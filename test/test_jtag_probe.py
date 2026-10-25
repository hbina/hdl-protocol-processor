"""Independent sixteen-state TAP and serial-register peer for JTAG firmware."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import First, Timer, ValueChange
from cocotb.utils import get_sim_time

from test import PinController, firmware, load_program, reset
from tools.runtime import Request

TRANSITIONS = {
    "reset": ("idle", "reset"),
    "idle": ("idle", "select_dr"),
    "select_dr": ("capture_dr", "select_ir"),
    "capture_dr": ("shift_dr", "exit1_dr"),
    "shift_dr": ("shift_dr", "exit1_dr"),
    "exit1_dr": ("pause_dr", "update_dr"),
    "pause_dr": ("pause_dr", "exit2_dr"),
    "exit2_dr": ("shift_dr", "update_dr"),
    "update_dr": ("idle", "select_dr"),
    "select_ir": ("capture_ir", "reset"),
    "capture_ir": ("shift_ir", "exit1_ir"),
    "shift_ir": ("shift_ir", "exit1_ir"),
    "exit1_ir": ("pause_ir", "update_ir"),
    "pause_ir": ("pause_ir", "exit2_ir"),
    "exit2_ir": ("shift_ir", "update_ir"),
    "update_ir": ("idle", "select_dr"),
}


class Tap:
    def __init__(self, dut):
        self.dut = dut
        self.state = "pause_dr"  # Exercise the firmware reset sequence.
        self.instruction = 31
        self.ir = self.dr = 0
        self.dr_width = 1
        self.data = 0x12345678
        self.captures = []
        self.updated_dr = None
        self.resets = 0
        self.last_rise = self.last_fall = self.last_tms_change = None

    async def run(self):
        previous = int(self.dut.uio_out.value)
        self.dut.uio_in.value = 0
        while True:
            await First(ValueChange(self.dut.uio_out), ValueChange(self.dut.uio_oe))
            now = int(self.dut.uio_out.value)
            time = get_sim_time(unit="ns")
            if (previous ^ now) & 2:
                self.last_tms_change = time
            if previous & 1 and now & 1:
                assert (previous ^ now) & 6 == 0, "JTAG control changed during TCK high"
            if not previous & 1 and now & 1:
                assert int(self.dut.uio_oe.value) == 7
                if self.last_rise is not None:
                    assert time - self.last_rise >= 10_000
                if self.last_fall is not None:
                    assert time - self.last_fall >= 5000
                if self.last_tms_change is not None:
                    assert time - self.last_tms_change >= 20
                self.last_rise = time
                tdi, tms = (now >> 2) & 1, (now >> 1) & 1
                if self.state == "capture_ir":
                    self.ir = 1  # Required low-order IR capture pattern 01.
                    self.captures.append({"kind": "ir", "tdi": []})
                elif self.state == "capture_dr":
                    self.dr_width = 32 if self.instruction in (1, 2) else 1
                    self.dr = (
                        0x0BADC0D1
                        if self.instruction == 1
                        else (self.data if self.instruction == 2 else 0)
                    )
                    self.captures.append({"kind": "dr", "tdi": []})
                elif self.state == "shift_ir":
                    self.captures[-1]["tdi"].append(tdi)
                    self.ir = (self.ir >> 1) | (tdi << 4)
                elif self.state == "shift_dr":
                    self.captures[-1]["tdi"].append(tdi)
                    self.dr = (self.dr >> 1) | (tdi << (self.dr_width - 1))
                self.state = TRANSITIONS[self.state][tms]
                if self.state == "reset":
                    self.instruction = 1
                    self.resets += 1
            elif previous & 1 and not now & 1:
                assert time - self.last_rise >= 5000
                self.last_fall = time
                if self.state == "update_ir":
                    self.instruction = self.ir
                elif self.state == "update_dr":
                    self.updated_dr = self.dr
                    if self.instruction == 2:
                        self.data = self.dr
                tdo = (
                    self.ir & 1
                    if self.state == "shift_ir"
                    else (self.dr & 1 if self.state == "shift_dr" else 0)
                )
                await Timer(1, unit="ps")
                self.dut.uio_in.value = tdo << 3
            previous = now


def shifted(value, width, incoming):
    outgoing = []
    for bit in incoming:
        outgoing.append(value & 1)
        value = (value >> 1) | (bit << (width - 1))
    return outgoing, value


async def scan(dut, controller, tap, ident, ir, payload, bits):
    assert len(payload) == (bits + 7) // 8
    incoming = [(payload[i // 8] >> (i % 8)) & 1 for i in range(bits)]
    initial = (
        1
        if ir
        else (
            0x0BADC0D1
            if tap.instruction == 1
            else (tap.data if tap.instruction == 2 else 0)
        )
    )
    width = 5 if ir else (32 if tap.instruction in (1, 2) else 1)
    expected, updated = shifted(initial, width, incoming)
    captures = len(tap.captures)
    request = Request(
        ident,
        1,
        arguments_length=2,
        input_count=len(payload),
        output_limit=len(payload),
    )
    await controller.submit(request, payload, bytes([int(ir), (bits - 1) % 8 + 1]))
    output, event = await controller.complete(request, poll_limit=100_000)
    received = []
    for index, (byte, metadata) in enumerate(output):
        assert metadata == 0
        valid = min(8, bits - index * 8)
        assert byte & ((1 << (8 - valid)) - 1) == 0
        byte >>= 8 - valid
        received.extend((byte >> bit) & 1 for bit in range(valid))
    assert received == expected
    assert event.status == 0 and event.detail == 0
    assert len(tap.captures) == captures + 1
    assert tap.captures[-1] == {"kind": "ir" if ir else "dr", "tdi": incoming}
    assert tap.state == "idle"
    assert (tap.instruction if ir else tap.updated_dr) == updated
    assert await controller.read(0x101) == 0
    assert int(dut.uio_out.value) == 0


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_jtag_probe_scans_and_readback(dut):
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut)
    tap = Tap(dut)
    cocotb.start_soon(tap.run())
    await load_program(dut, firmware("jtag_probe.asm"))
    await Timer(70, unit="us")
    assert tap.state == "idle" and tap.instruction == 1 and tap.resets >= 1
    resets = tap.resets
    controller = PinController(dut, 0x4A544147)
    await scan(dut, controller, tap, 1, False, bytes(4), 32)  # IDCODE.
    await scan(dut, controller, tap, 2, True, b"\xe2", 5)  # Upper padding ignored.
    rng = random.Random(0x4A544147)
    for ident, bits in enumerate([1, 7, 8, 9, 31, 32, 33, 511, 512], 10):
        tap.data = rng.getrandbits(32)
        payload = bytes(rng.randrange(256) for _ in range((bits + 7) // 8))
        await scan(dut, controller, tap, ident, False, payload, bits)
    await scan(dut, controller, tap, 30, False, bytes.fromhex("efbeadde"), 32)
    assert tap.data == 0xDEADBEEF
    await scan(dut, controller, tap, 31, False, bytes(4), 32)
    await scan(dut, controller, tap, 32, True, b"\x1f", 5)
    await scan(dut, controller, tap, 33, False, b"\x55\x01", 9)  # BYPASS.
    assert tap.resets == resets, "firmware reset the TAP between requests"
