"""Independent serial PHY boundary, frame/FCS oracle and clock-phase experiments."""

import os
import random
import zlib

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Event, First, RisingEdge, Timer, ValueChange
from cocotb.utils import get_sim_time
from run_wave_c import candidate_words, study_assembler

from test import PinController, load_program, reset
from tools.runtime import Request


def body(rng):
    return bytes.fromhex("ffffffffffff02000000000188b5") + bytes(
        rng.randrange(256) for _ in range(46)
    )


def framed(data):
    return b"\x55" * 7 + b"\xd5" + data + zlib.crc32(data).to_bytes(4, "little")


class Phy:
    def __init__(self, dut):
        self.dut = dut
        self.tx_clock = self.rx_clock = 0
        self.rxd = self.crs = 0
        self.wake = Event()
        self.frames = []
        self.tx_bits = []
        self.tx_active = False
        self.last_tx_end = None
        self.tx_data_changed = self.tx_enable_changed = 0
        self.pending = None
        self.rx_bits = None
        self.rx_index = 0

    async def inputs(self):
        while True:
            self.dut.uio_in.value = (
                self.tx_clock << 2 | self.rxd << 3 | self.rx_clock << 4 | self.crs << 5
            )
            self.wake.clear()
            await self.wake.wait()
            await Timer(1, unit="ps")

    async def tx_signals(self):
        previous_data = previous_enable = 0
        while True:
            await First(ValueChange(self.dut.uio_out), ValueChange(self.dut.uio_oe))
            oe, out = int(self.dut.uio_oe.value), int(self.dut.uio_out.value)
            data, enable = int(bool(oe & out & 1)), int(bool(oe & out & 2))
            now = get_sim_time(unit="ps")
            if data != previous_data:
                self.tx_data_changed = now
            if enable != previous_enable:
                self.tx_enable_changed = now
            previous_data, previous_enable = data, enable

    async def tx_clock_run(self, phase_ps=1, high_ps=25_000):
        await Timer(phase_ps, unit="ps")
        while True:
            self.tx_clock ^= 1
            self.wake.set()
            if self.tx_clock:
                await Timer(2, unit="ps")
                oe, out = int(self.dut.uio_oe.value), int(self.dut.uio_out.value)
                assert not oe & ~3
                enabled = bool(oe & out & 2)  # PHY TX_EN has external pull-down.
                if enabled or self.tx_active:
                    assert get_sim_time(unit="ps") - self.tx_enable_changed >= 25_000, (
                        "TX_EN setup to PHY clock"
                    )
                if enabled:
                    assert get_sim_time(unit="ps") - self.tx_data_changed >= 25_000, (
                        "TXD setup to PHY clock"
                    )
                    if not self.tx_active:
                        if self.last_tx_end is not None:
                            assert get_sim_time(unit="ns") - self.last_tx_end >= 9600, (
                                "Ethernet interframe gap"
                            )
                        self.tx_bits = []
                    self.tx_bits.append(out & 1)
                elif self.tx_active:
                    assert len(self.tx_bits) % 8 == 0
                    packet = bytes(
                        sum(self.tx_bits[i + j] << j for j in range(8))
                        for i in range(0, len(self.tx_bits), 8)
                    )
                    self.frames.append(packet)
                    self.last_tx_end = get_sim_time(unit="ns")
                self.tx_active = enabled
                await Timer(high_ps - 2, unit="ps")
            else:
                await Timer(100_000 - high_ps, unit="ps")

    async def rx_clock_run(self, phase_ps=1, ppm=0):
        await Timer(phase_ps, unit="ps")
        half_ps = round(50_000 / (1 + ppm / 1_000_000))
        while True:
            self.rx_clock ^= 1
            if self.rx_clock:
                if self.rx_bits is not None:
                    self.rx_index += 1
            else:
                if self.rx_bits is None and self.pending is not None:
                    packet, self.pending = self.pending, None
                    self.rx_bits = [
                        (byte >> bit) & 1 for byte in packet for bit in range(8)
                    ]
                    self.rx_index = 0
                if self.rx_bits is not None:
                    if self.rx_index < len(self.rx_bits):
                        self.crs = 1
                        self.rxd = self.rx_bits[self.rx_index]
                    else:
                        self.crs, self.rxd, self.rx_bits = 0, 0, None
            self.wake.set()
            await Timer(half_ps, unit="ps")

    async def send(self, packet):
        assert self.pending is None and self.rx_bits is None
        self.pending = packet
        while self.pending is not None or self.rx_bits is not None:
            await Timer(100, unit="ns")


async def setup(dut, *, phase_ps=1, ppm=0):
    assert os.environ.get("WAVE_C_CAPACITY_EXPERIMENT") == "ethernet"
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut)
    phy = Phy(dut)
    cocotb.start_soon(phy.inputs())
    cocotb.start_soon(phy.tx_signals())
    phy.tx_task = cocotb.start_soon(phy.tx_clock_run())
    rx_clock = cocotb.start_soon(phy.rx_clock_run(phase_ps, ppm))
    await load_program(dut, candidate_words("ethernet"))
    return PinController(dut, 0x455448), phy, rx_clock


async def transact(
    dut, controller, ident, *, tx=None, packet=None, phy=None, status=0, expected=b""
):
    receive = tx is None
    request = Request(
        ident,
        1,
        arguments_length=1,
        input_count=0 if receive else len(tx),
        output_limit=64 if receive else 0,
    )
    await controller.submit(request, b"" if receive else tx, bytes([int(receive)]))
    if packet is not None:
        await Timer(10, unit="us")
        sender = cocotb.start_soon(phy.send(packet))
    else:
        sender = None
    output, event = await controller.complete(request, poll_limit=100_000)
    if sender:
        await sender
    assert event.status == status, event
    assert output == [(byte, 0) for byte in expected], (event, output)
    assert int(dut.uio_oe.value) == 1
    assert await controller.read(0x101) == 0


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def test_wave_c_generic_addressing(dut):
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut)
    lines = ["HALT"] * 512
    for index, instruction in {
        0: "JMP 260",
        260: "LDI r0, 0",
        261: "JZ r0, 300",
        300: "LDI r2, 2",
        301: "DJNZ r2, 301",
        302: "CMPI r2, 1",
        303: "JFAIL 400",
        400: "CMPI r2, 0",
        401: "JFAIL 499",
        402: "LDI r0, 0x5a",
        403: "LDI r3, 0xa5",
        404: "JMP 511",
        511: "HALT",
    }.items():
        lines[index] = instruction
    # Both 9-bit PC/loader and branch bank bits matter; finish at the last word.
    await load_program(dut, study_assembler().assemble("\n".join(lines)))
    await Timer(600, unit="ns")
    dut.ena.value = 0
    controller = PinController(dut)
    assert await controller.read(0x10B) == 0x5A
    assert await controller.read(0x10E) == 0xA5


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_ethernet_candidate_tx_rx(dut):
    controller, phy, _ = await setup(dut)
    rng = random.Random(0x455448)
    for ident in range(3):
        data = body(rng)
        frames = len(phy.frames)
        await transact(dut, controller, ident * 2, tx=data)
        assert len(phy.frames) == frames + 1
        assert phy.frames[-1] == framed(data)
        reply = framed(body(rng))
        await transact(
            dut, controller, ident * 2 + 1, packet=reply, phy=phy, expected=reply[8:]
        )


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_ethernet_candidate_bad_frames(dut):
    controller, phy, _ = await setup(dut)
    packet = framed(body(random.Random(42)))
    corrupt = bytearray(packet)
    corrupt[25] ^= 0x80
    await transact(dut, controller, 100, packet=bytes(corrupt), phy=phy, status=16)
    await transact(dut, controller, 101, packet=packet[:-7], phy=phy, status=16)
    await transact(dut, controller, 102, packet=packet + b"\x00", phy=phy, status=17)
    await transact(dut, controller, 103, phy=phy, status=6)
    await transact(dut, controller, 104, packet=b"\x55" * 72, phy=phy, status=6)
    await transact(dut, controller, 105, packet=packet, phy=phy, expected=packet[8:])
    await transact(dut, controller, 106, packet=framed(b"\x00" * 8), phy=phy, status=16)
    await transact(
        dut, controller, 107, packet=packet[6:], phy=phy, expected=packet[8:]
    )


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_ethernet_candidate_clock_phase(dut):
    controller, phy, rx_clock = await setup(dut)
    packet = framed(body(random.Random(20261024)))
    ident = 200
    for phase in [1, 5_000, 10_000, 15_000, 19_999]:
        for ppm in [-100, 0, 100]:
            rx_clock.cancel()
            await RisingEdge(dut.clk)
            await Timer(1, unit="ps")
            phy.rx_clock = 0
            phy.wake.set()
            rx_clock = cocotb.start_soon(phy.rx_clock_run(phase, ppm))
            dut._log.info("RX phase=%d ps, relative frequency=%d ppm", phase, ppm)
            await transact(
                dut, controller, ident, packet=packet, phy=phy, expected=packet[8:]
            )
            ident += 1


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def test_ethernet_candidate_missing_rx_clock(dut):
    controller, phy, rx_clock = await setup(dut)
    rx_clock.cancel()
    for ident, stuck in enumerate([0, 1], 300):
        phy.rx_clock, phy.crs = stuck, 1
        phy.wake.set()
        await transact(dut, controller, ident, phy=phy, status=6)
    phy.crs, phy.rx_clock = 0, 0
    phy.wake.set()
    cocotb.start_soon(phy.rx_clock_run())
    packet = framed(body(random.Random(300)))
    await transact(dut, controller, 302, packet=packet, phy=phy, expected=packet[8:])


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_ethernet_candidate_tx_duty_setup(dut):
    controller, phy, _ = await setup(dut)
    data = body(random.Random(400))
    ident = 400
    for phase in [1, 5_000, 10_000, 15_000, 19_999]:
        for high_ps in [20_000, 25_000, 30_000]:
            phy.tx_task.cancel()
            await RisingEdge(dut.clk)
            await Timer(1, unit="ps")
            phy.tx_clock = 0
            phy.wake.set()
            phy.tx_task = cocotb.start_soon(phy.tx_clock_run(phase, high_ps))
            dut._log.info(
                "TX phase=%d ps, HIGH=%d ps; setup requirement 25000 ps", phase, high_ps
            )
            frames = len(phy.frames)
            await transact(dut, controller, ident, tx=data)
            assert len(phy.frames) == frames + 1 and phy.frames[-1] == framed(data)
            ident += 1
