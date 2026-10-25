"""Independent PS/2 device and open-drain resolver; clock is device-generated."""

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Event, First, Timer, ValueChange, with_timeout
from cocotb.utils import get_sim_time

from test import PinController, load_program, reset
from tools.runtime import Request
from run_wave_b import candidate_words


class Device:
    def __init__(self, dut):
        self.dut = dut
        self.clock_low = self.data_low = False
        self.wake, self.changed = Event(), Event()
        self.value = 3
        self.commands = []

    async def resolve(self):
        self.dut.uio_in.value = 3
        while True:
            oe, out = int(self.dut.uio_oe.value), int(self.dut.uio_out.value)
            assert not oe & ~7
            assert not oe & out & 3, "PS/2 controller drove a high level"
            resolved = (~(oe | int(self.clock_low) | (int(self.data_low) << 1))) & 3
            self.dut.uio_in.value = resolved
            if resolved != self.value:
                self.value = resolved
                self.changed.set()
            self.wake.clear()
            await First(
                ValueChange(self.dut.uio_oe),
                ValueChange(self.dut.uio_out),
                self.wake.wait(),
            )
            await Timer(1, unit="ps")

    async def level(self, mask, value):
        while self.value & mask != value:
            self.changed.clear()
            await self.changed.wait()

    async def command(self, *, half_us=40, ack=True, clocks=True):
        await with_timeout(self.level(1, 0), 5, "ms")
        inhibited = get_sim_time(unit="ns")
        await with_timeout(self.level(1, 1), 5, "ms")
        assert get_sim_time(unit="ns") - inhibited >= 100_000
        assert not self.value & 2, "missing host request-to-send start"
        if not clocks:
            await Timer(2, unit="ms")
            return None
        incoming = []
        await Timer(half_us, unit="us")
        for _ in range(10):
            self.clock_low = True
            self.wake.set()
            await Timer(half_us, unit="us")
            incoming.append((self.value >> 1) & 1)
            self.clock_low = False
            self.wake.set()
            await Timer(half_us, unit="us")
        byte = sum(bit << i for i, bit in enumerate(incoming[:8]))
        assert incoming[8] == (1 ^ (byte.bit_count() % 2)), "host odd parity"
        assert incoming[9] == 1, "host stop bit"
        assert not int(self.dut.uio_oe.value) & 2, "host must release for ACK"
        self.commands.append(byte)
        self.clock_low, self.data_low = True, ack
        self.wake.set()
        await Timer(half_us, unit="us")
        self.clock_low = False
        self.wake.set()
        await Timer(half_us, unit="us")
        self.data_low = False
        self.wake.set()
        return byte

    async def send(
        self,
        payload,
        *,
        half_us=40,
        bad_parity=False,
        bad_stop=False,
        bad_start=False,
        stall_bit=None,
    ):
        for index, byte in enumerate(payload):
            bits = [1 if bad_start else 0] + [(byte >> i) & 1 for i in range(8)]
            bits += [
                1
                ^ (byte.bit_count() % 2)
                ^ bool(bad_parity and index == len(payload) - 1)
            ]
            bits += [0 if bad_stop and index == len(payload) - 1 else 1]
            for bit_index, bit in enumerate(bits):
                self.data_low = not bool(bit)
                self.wake.set()
                await Timer(half_us, unit="us")
                self.clock_low = True
                self.wake.set()
                if stall_bit == bit_index:
                    return
                await Timer(half_us, unit="us")
                self.clock_low = False
                self.wake.set()
        self.data_low = False
        self.wake.set()

    async def armed(self):
        for _ in range(10_000):
            if int(self.dut.uio_out.value) & 4:
                await Timer(1, unit="us")
                return
            await Timer(1, unit="us")
        raise AssertionError("PS/2 receiver did not arm")

    async def response(self, command, reply, **options):
        received = await self.command(**options)
        assert received == command
        # Device-generated response begins independently of host polling.
        # Leave a real released interval after the wire ACK before START.
        await Timer(50, unit="us")
        await self.send(reply, half_us=options.get("half_us", 40))


async def setup(dut):
    assert os.environ.get("WAVE_B_CAPACITY_EXPERIMENT") == "ps2"
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=3)
    device = Device(dut)
    cocotb.start_soon(device.resolve())
    await load_program(dut, candidate_words("ps2"))
    return PinController(dut, 0x505332), device


async def complete(dut, controller, request, *, expected=b"", status=0):
    output, event = await controller.complete(request, poll_limit=200_000)
    assert output == [(byte, 0) for byte in expected], event
    assert event.status == status and event.detail == 0
    assert int(dut.uio_out.value) == 0 and int(dut.uio_oe.value) == 4
    assert await controller.read(0x101) == 0


async def receive(
    dut,
    controller,
    device,
    ident,
    payload,
    *,
    count=None,
    expected=None,
    status=0,
    **options,
):
    count = len(payload) if count is None else count
    request = Request(ident, 1, arguments_length=1, output_limit=count)
    await controller.submit(request, b"", bytes([count]))
    await device.armed()
    sender = cocotb.start_soon(device.send(payload, **options)) if payload else None
    await complete(
        dut,
        controller,
        request,
        expected=payload if expected is None else expected,
        status=status,
    )
    if sender:
        await with_timeout(sender, 100, "ms")


@cocotb.test(timeout_time=500, timeout_unit="ms")
async def test_ps2_candidate_commands_and_receive(dut):
    controller, device = await setup(dut)
    for ident, command in enumerate([0xED, 7, 0x00, 0xFF, 0x55, 0xAA]):
        peer = cocotb.start_soon(device.response(command, b"\xfa"))
        request = Request(ident, 1, arguments_length=1, input_count=1, output_limit=1)
        await controller.submit(request, bytes([command]), b"\x01")
        await complete(dut, controller, request, expected=b"\xfa")
        await with_timeout(peer, 5, "ms")
    assert device.commands == [0xED, 7, 0x00, 0xFF, 0x55, 0xAA]
    rng = random.Random(0x505332)
    await receive(
        dut,
        controller,
        device,
        20,
        bytes(rng.randrange(256) for _ in range(64)),
        half_us=30,
    )
    for ident, half_us in enumerate([30, 40, 50], 30):
        await receive(
            dut, controller, device, ident, b"\x00\xff\x55\xaa", half_us=half_us
        )


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_ps2_candidate_errors_and_recovery(dut):
    controller, device = await setup(dut)
    for ident, options, status in [
        (100, {"bad_parity": True}, 15),
        (101, {"bad_stop": True}, 14),
        (102, {"bad_start": True}, 14),
    ]:
        await receive(
            dut,
            controller,
            device,
            ident,
            b"\x34",
            expected=b"",
            status=status,
            **options,
        )
        await receive(dut, controller, device, ident + 10, b"\xa5")
    await receive(dut, controller, device, 120, b"", count=1, expected=b"", status=6)
    await receive(
        dut, controller, device, 121, b"\x12", count=2, expected=b"\x12", status=6
    )
    for ident, options, status in [
        (130, {"ack": False}, 13),
        (131, {"clocks": False}, 6),
    ]:
        peer = cocotb.start_soon(device.command(**options))
        request = Request(ident, 1, arguments_length=1, input_count=1)
        await controller.submit(request, b"\xed", b"\x00")
        await complete(dut, controller, request, status=status)
        await with_timeout(peer, 5, "ms")
    await receive(
        dut, controller, device, 140, b"\xff", expected=b"", status=6, stall_bit=5
    )
    device.clock_low = device.data_low = False
    device.wake.set()
    await Timer(100, unit="us")
    await receive(dut, controller, device, 141, b"\x81")
