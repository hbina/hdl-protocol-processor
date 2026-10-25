"""Independent frame oracle, receiving CAN node and transmitter fault tests."""

import os
import random

import cocotb
from can_peer import Bus, frame
from cocotb.clock import Clock
from cocotb.triggers import Timer, ValueChange
from cocotb.utils import get_sim_time
from run_can_tx import candidate_words

from test import PinController, load_program, reset
from tools.runtime import Request


class Receiver(Bus):
    async def listen(
        self,
        identifier,
        data,
        *,
        ack=True,
        collision=None,
        winner=None,
        ppm=0,
        ack_delay_ns=0,
        tail_error=None,
    ):
        # All expected bits come from the peer's own frame encoder/long-division
        # CRC, never from the firmware, RAM or instruction trace.
        wire, ack_index, _ = frame(identifier, data)
        bad_tail = (
            {
                "crc_delimiter": ack_index - 1,
                "ack_delimiter": ack_index + 1,
                "eof": ack_index + 4,
            }[tail_error]
            if tail_error
            else None
        )
        while self.drive() != 0:
            await ValueChange(self.dut.uio_out)
            await Timer(1, unit="ps")
        start = get_sim_time(unit="ns")
        bit_ns = round(8000 / (1 + ppm / 1_000_000))
        winner_wire = frame(winner, data)[0] if winner is not None else None
        if winner_wire:
            # A third simulated node ACKs the winning transmitter. This probe
            # checks the loser's release; receiving the winner remains open.
            winner_ack = frame(winner, data)[1]
            winner_wire[winner_ack] = 0
        loss = (
            next(
                i
                for i, (ours, theirs) in enumerate(zip(wire, winner_wire))
                if ours != theirs
            )
            if winner_wire is not None
            else collision
        )
        if winner_wire:
            assert wire[loss] == 1 and winner_wire[loss] == 0 and loss < 14
        # A loss test follows the winning frame; otherwise check the DUT frame.
        count = len(winner_wire) if winner_wire else len(wire)
        for index in range(count):
            if winner_wire:
                self.sender = winner_wire[index]
            elif index == collision:
                assert wire[index] == 1 and index > 0
                self.sender = 0
            elif index == bad_tail:
                self.sender = 0
            else:
                self.sender = 1
            if ack and winner is None and collision is None and index == ack_index:
                if ack_delay_ns:
                    await Timer(ack_delay_ns, unit="ns")
                self.sender = 0
            else:
                assert not ack_delay_ns or index != ack_index or not ack
            offset = (
                ack_delay_ns
                if ack and winner is None and collision is None and index == ack_index
                else 0
            )
            await Timer(bit_ns * 3 // 4 - offset, unit="ns")
            expected = 1 if loss is not None and index > loss else wire[index]
            assert self.drive() == expected, (index, self.drive(), expected)
            await Timer(bit_ns - bit_ns * 3 // 4, unit="ns")
        self.sender = 1
        # Every actual TX transition before a deliberately aborted cell lies on
        # the transmitter's 8us grid, even while peer sampling has clock error.
        for when, _value in self.ack_edges:
            if when >= start - 1 and (
                loss is None or when < start + (loss + 0.75) * bit_ns
            ):
                phase = (when - start) % 8000
                assert min(phase, 8000 - phase) <= 10, (when, start, phase)
        return start, bit_ns, count


async def setup(dut):
    assert os.environ.get("WAVE_C_CAPACITY_EXPERIMENT") == "can_tx"
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    bus = Receiver(dut)
    cocotb.start_soon(bus.resolve())
    await load_program(dut, candidate_words("can_tx"))
    return PinController(dut, 0x545843), bus


async def transmit(controller, bus, ident, identifier, data, *, status=0, **kwargs):
    request = Request(ident, 1, arguments_length=3, input_count=len(data))
    listener = cocotb.start_soon(bus.listen(identifier, data, **kwargs))
    await controller.submit(
        request, data, bytes([identifier >> 8, identifier & 255, len(data)])
    )
    output, event = await controller.complete(request, poll_limit=30000)
    completed_at = get_sim_time(unit="ns")
    start, bit_ns, count = await listener
    assert output == [] and event.status == status, (output, event)
    assert event.input_consumed == len(data) and event.output_produced == 0, event
    assert bus.drive() == 1
    if status == 0:
        assert completed_at >= start + count * bit_ns, "success before end/intermission"
    assert await controller.read(0x101) == 0


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_can_transmit_frames(dut):
    controller, bus = await setup(dut)
    rng = random.Random(0x43414E)
    for length in range(9):
        await transmit(
            controller,
            bus,
            length,
            rng.randrange(2048),
            bytes(rng.randrange(256) for _ in range(length)),
        )
    await transmit(controller, bus, 10, 0, bytes(8))
    await transmit(controller, bus, 11, 0x7FF, b"\xff" * 8)
    for identifier in range(2048):
        _wire, ack_index, stuffing = frame(identifier, b"\xa5")
        if stuffing and stuffing[-1] == ack_index - 2:
            await transmit(controller, bus, 12, identifier, b"\xa5")
            break
    else:
        raise AssertionError("No final CRC stuff vector")


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_can_transmit_faults_recovery(dut):
    controller, bus = await setup(dut)
    await transmit(controller, bus, 20, 0x123, b"\xff" * 8, ack=False, status=24)
    wire, ack_index, _ = frame(0x123, b"\xff" * 8)
    collision = next(index for index in range(25, ack_index - 20) if wire[index])
    await transmit(
        controller, bus, 21, 0x123, b"\xff" * 8, collision=collision, status=21
    )
    await transmit(controller, bus, 22, 0x7FF, b"\xff" * 8, winner=0x3FF, status=22)
    stuffed_wire, _ack, stuffing = frame(0, bytes(8))
    stuffed_collision = next(index for index in stuffing if stuffed_wire[index])
    await transmit(
        controller, bus, 23, 0, bytes(8), collision=stuffed_collision, status=21
    )
    await transmit(controller, bus, 24, 0x321, b"\x55\xaa")
    for ident, tail_error in enumerate(["crc_delimiter", "ack_delimiter", "eof"], 25):
        await transmit(
            controller, bus, ident, 0x456, b"\xa5", tail_error=tail_error, status=17
        )
    await transmit(controller, bus, 28, 0x321, b"\x55\xaa")


@cocotb.test(timeout_time=40, timeout_unit="ms")
async def test_can_transmit_peer_clock_ack_delay(dut):
    controller, bus = await setup(dut)
    ident = 100
    for ppm in [-1000, 0, 1000]:
        for delay in [0, 400, 800]:
            await transmit(
                controller,
                bus,
                ident,
                0x456,
                b"\x55\xaa\x00\xff\x12\x34\x56\x78",
                ppm=ppm,
                ack_delay_ns=delay,
            )
            ident += 1


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def test_can_transmit_busy_timeout(dut):
    controller, bus = await setup(dut)
    bus.sender = 0
    request = Request(200, 1, arguments_length=3, input_count=8)
    await controller.submit(request, b"\x01" * 8, b"\x01\x23\x08")
    output, event = await controller.complete(request, poll_limit=30000)
    assert output == [] and event.status == 6 and event.input_consumed == 8, event
    assert bus.drive() == 1
    bus.sender = 1
    await transmit(controller, bus, 201, 0x456, b"\x5a")
