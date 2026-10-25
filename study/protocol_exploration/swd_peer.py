"""Independent SWD DP target: wire ownership, request parity, ACK and data phases."""

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import First, Timer, ValueChange
from cocotb.utils import get_sim_time

from test import PinController, load_program, reset
from tools.runtime import Request
from run_wave_b import candidate_words


class SwdTarget:
    def __init__(self, dut):
        self.dut = dut
        self.mode = "unsynchronized"
        self.drive = False
        self.bit = 1
        self.ones = 0
        self.resets = 0
        self.last_rise = self.last_fall = None
        self.sticky_fault = False
        self.select = self.control = 0
        self.read_buffer = 0x12345678
        self.writes = []
        self.requests = []
        self.arm()

    def arm(self, *, acks=(), bad_parity=False):
        self.acks = list(acks)
        self.bad_parity = bad_parity

    def register_read(self, address):
        return [0x2BA01477, self.control, 0, self.read_buffer][address]

    def register_write(self, address, value):
        self.writes.append((address, value))
        if address == 0:
            if value & 0x1E:
                self.sticky_fault = False
        elif address == 1:
            self.control = value & 0x50000000
            self.control |= (self.control << 1) & 0xA0000000
        elif address == 2:
            self.select = value & 0xFF0000F0

    def rising(self, data, host_drives):
        self.ones = self.ones + 1 if data else 0
        if self.ones >= 50 and host_drives:
            if self.ones == 50:
                self.resets += 1
            self.mode, self.drive = "idle", False
            return
        if self.mode == "idle":
            if data and host_drives:
                self.header = [1]
                self.mode = "request"
        elif self.mode == "request":
            assert host_drives
            self.header.append(data)
            if len(self.header) == 8:
                start, ap, self.read, a2, a3, parity, stop, park = self.header
                assert (start, ap, stop, park) == (1, 0, 0, 1)
                assert parity == (self.read ^ a2 ^ a3)
                self.address = a2 | (a3 << 1)
                self.requests.append((self.read, self.address))
                self.ack = (
                    self.acks.pop(0)
                    if self.acks
                    else (
                        4
                        if self.sticky_fault
                        and not (not self.read and self.address == 0)
                        else 1
                    )
                )
                if self.ack == 4:
                    self.sticky_fault = True
                self.mode = "request_end"
        elif self.mode == "turn_target":
            assert not host_drives and not self.drive
            self.mode = "turn_target_end"
        elif self.mode == "ack":
            assert not host_drives
            assert data == ((self.ack >> self.index) & 1)
            self.index += 1
            if self.index == 3:
                self.mode = "ack_end"
        elif self.mode == "read_data":
            assert not host_drives
            assert data == self.outgoing[self.index]
            self.index += 1
            if self.index == 33:
                self.mode = "read_end"
        elif self.mode == "turn_host":
            assert not host_drives and not self.drive
            self.mode = "turn_host_end"
        elif self.mode == "write_data":
            assert host_drives and not self.drive
            self.incoming.append(data)
            if len(self.incoming) == 33:
                value = sum(bit << i for i, bit in enumerate(self.incoming[:32]))
                assert self.incoming[-1] == value.bit_count() % 2
                self.register_write(self.address, value)
                self.mode = "write_end"

    def falling(self):
        if self.mode == "request_end":
            self.mode, self.drive = "turn_target", False
        elif self.mode == "turn_target_end":
            self.mode, self.index, self.drive = "ack", 0, True
            self.bit = self.ack & 1
        elif self.mode == "ack":
            self.bit = (self.ack >> self.index) & 1
        elif self.mode == "ack_end":
            if self.ack == 1 and self.read:
                value = self.register_read(self.address)
                self.outgoing = [(value >> i) & 1 for i in range(32)] + [
                    value.bit_count() % 2 ^ self.bad_parity
                ]
                self.mode, self.index = "read_data", 0
                self.bit = self.outgoing[0]
            else:
                self.mode, self.drive = "turn_host", False
        elif self.mode == "read_data":
            self.bit = self.outgoing[self.index]
        elif self.mode == "read_end":
            self.mode, self.drive = "turn_host", False
        elif self.mode == "turn_host_end":
            if self.ack == 1 and not self.read:
                self.mode, self.incoming = "write_data", []
            else:
                self.mode = "idle"
        elif self.mode == "write_end":
            self.mode = "idle"

    async def run(self):
        previous = int(self.dut.uio_out.value)
        self.dut.uio_in.value = 2
        while True:
            await First(ValueChange(self.dut.uio_out), ValueChange(self.dut.uio_oe))
            now, oe = int(self.dut.uio_out.value), int(self.dut.uio_oe.value)
            time = get_sim_time(unit="ns")
            assert not (oe & 2 and self.drive), "SWDIO driver overlap"
            assert not oe & ~3
            data = self.bit if self.drive else ((now >> 1) & 1 if oe & 2 else 1)
            if not previous & 1 and now & 1:
                assert oe & 1
                if self.last_rise is not None:
                    assert time - self.last_rise >= 10_000
                if self.last_fall is not None:
                    assert time - self.last_fall >= 5000
                self.last_rise = time
                self.rising(data, bool(oe & 2))
            elif previous & 1 and not now & 1:
                assert time - self.last_rise >= 5000
                self.last_fall = time
                self.falling()
            assert not (oe & 2 and self.drive), "SWDIO driver overlap after edge"
            data = self.bit if self.drive else ((now >> 1) & 1 if oe & 2 else 1)
            await Timer(1, unit="ps")
            self.dut.uio_in.value = data << 1
            previous = now


async def setup(dut):
    assert os.environ.get("WAVE_B_CAPACITY_EXPERIMENT") == "swd"
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    target = SwdTarget(dut)
    cocotb.start_soon(target.run())
    await load_program(dut, candidate_words("swd"))
    await Timer(700, unit="us")
    assert target.resets == 1
    return PinController(dut, 0x535744), target


async def transfer(
    dut, controller, ident, read, address, value=0, *, status=0, expected=None
):
    payload = b"" if read else value.to_bytes(4, "little")
    request = Request(
        ident,
        1,
        arguments_length=2,
        input_count=len(payload),
        output_limit=4 if read else 0,
    )
    await controller.submit(request, payload, bytes([int(read), address]))
    output, event = await controller.complete(request, poll_limit=100_000)
    assert event.status == status and event.detail == 0
    assert output == (
        []
        if expected is None
        else [(byte, 0) for byte in expected.to_bytes(4, "little")]
    )
    assert int(dut.uio_oe.value) == 3 and int(dut.uio_out.value) == 0
    assert await controller.read(0x101) == 0


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_swd_candidate_register_transfers(dut):
    controller, target = await setup(dut)
    await transfer(dut, controller, 1, True, 0, expected=0x2BA01477)
    rng = random.Random(0x535744)
    for ident in range(8):
        value = rng.getrandbits(32) & 0xFF0000F0
        await transfer(dut, controller, 10 + ident * 2, False, 2, value)
        assert target.select == value
        target.read_buffer = rng.getrandbits(32)
        await transfer(
            dut, controller, 11 + ident * 2, True, 3, expected=target.read_buffer
        )
    await transfer(dut, controller, 30, False, 1, 0x50000000)
    await transfer(dut, controller, 31, True, 1, expected=0xF0000000)
    assert target.resets == 1


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_swd_candidate_wait_fault_parity(dut):
    controller, target = await setup(dut)
    target.arm(acks=[2, 2, 1])
    writes = len(target.writes)
    await transfer(dut, controller, 100, False, 2, 0xA50000C0)
    assert target.select == 0xA50000C0 and len(target.writes) == writes + 1
    target.arm(acks=[2, 2, 2])
    await transfer(dut, controller, 101, False, 2, 0xB60000D0, status=10)
    assert len(target.writes) == writes + 1
    target.arm(acks=[4])
    await transfer(dut, controller, 102, True, 0, status=11)
    target.arm()
    await transfer(dut, controller, 103, True, 0, status=11)
    await transfer(dut, controller, 104, False, 0, 0x1E)  # ABORT clears sticky fault.
    target.arm(bad_parity=True)
    await transfer(dut, controller, 105, True, 0, status=12)
    target.arm()
    await transfer(dut, controller, 106, True, 0, expected=0x2BA01477)
    assert target.resets == 1
