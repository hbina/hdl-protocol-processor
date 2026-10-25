"""Independent Classical CAN transmitter and wired-dominant transceiver model.

This initial receive milestone checks firmware live CRC/ACK, not complete node
conformance. Peer CRC uses polynomial division, independently of firmware LFSR.
"""

import os
import random
from itertools import pairwise
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ValueChange
from cocotb.utils import get_sim_time
from run_can import candidate_words, study_assembler

from test import PinController, load_program, reset
from tools.runtime import Request


def bits(value, width):
    return [(value >> index) & 1 for index in reversed(range(width))]


def crc15(sequence):
    # Long division of message*x^15 by x^15+x^14+x^10+x^8+x^7+x^4+x^3+1.
    dividend = 0
    for bit in sequence:
        dividend = dividend << 1 | bit
    dividend <<= 15
    while dividend.bit_length() > 15:
        dividend ^= 0xC599 << (dividend.bit_length() - 16)
    return bits(dividend, 15)


def frame(identifier, data, *, crc_error=False, header_flags=(0, 0, 0), dlc=None):
    logical = (
        [0]
        + bits(identifier, 11)
        + list(header_flags)
        + bits(len(data) if dlc is None else dlc, 4)
    )
    logical += [bit for byte in data for bit in bits(byte, 8)]
    check = crc15(logical)
    if crc_error:
        check[-1] ^= 1
    logical += check
    wire = []
    previous, count = None, 0
    stuff_positions = []
    for bit in logical:
        wire.append(bit)
        count = count + 1 if bit == previous else 1
        previous = bit
        if count == 5:
            wire.append(1 - bit)
            stuff_positions.append(len(wire) - 1)
            previous, count = 1 - bit, 1
    # CRC delimiter, ACK slot, ACK delimiter, EOF7, intermission3.
    return wire + [1] * 13, len(wire) + 1, stuff_positions


class Bus:
    def __init__(self, dut):
        self.dut = dut
        self.sender = 1
        self.ack_edges = []
        self.last_drive = 1
        self.samples = []

    async def sample_trace(self):
        # Observe only timing of real instruction execution. Wire/data oracles
        # above remain independent of the implementation and instruction trace.
        source = Path(__file__).with_name("can_candidate.asm").read_text()
        _, labels = study_assembler()._parse_lines(source)
        core = self.dut.user_project.core
        while True:
            await ValueChange(core.pc)
            await Timer(1, unit="ps")
            if int(core.pc.value) == labels["sample"]:
                # WAIT advances PC when issued, before its counter expires.
                while int(core.wait_count.value):
                    await RisingEdge(self.dut.clk)
                    await Timer(1, unit="ps")
                await RisingEdge(self.dut.clk)
                self.samples.append(get_sim_time(unit="ns"))

    def drive(self):
        oe, out = int(self.dut.uio_oe.value), int(self.dut.uio_out.value)
        assert oe in (0, 1), oe
        return (out & 1) if oe & 1 else 1

    async def resolve(self):
        while True:
            drive = self.drive()
            if drive != self.last_drive:
                self.ack_edges.append((get_sim_time(unit="ns"), drive))
                self.last_drive = drive
            self.dut.uio_in.value = (self.sender & drive) << 1
            await Timer(10, unit="ns")

    async def send(self, wire, ack_index, *, ppm=0, phase_ns=1, acknowledge=True):
        bit_ns = round(8000 / (1 + ppm / 1_000_000))
        await Timer(phase_ns, unit="ns")
        start = get_sim_time(unit="ns")
        edge_start = len(self.ack_edges)
        sampled = []
        for index, bit in enumerate(wire):
            self.sender = bit
            await Timer(bit_ns * 3 // 4, unit="ns")
            drive = self.drive()
            sampled.append(drive)
            if index == ack_index:
                assert drive == int(not acknowledge), (index, drive, self.ack_edges)
            else:
                assert drive == 1, (index, "unexpected dominant", self.ack_edges)
            await Timer(bit_ns - bit_ns * 3 // 4, unit="ns")
        self.sender = 1
        edges = self.ack_edges[edge_start:]
        if acknowledge:
            assert len(edges) == 2 and [value for _, value in edges] == [0, 1], edges
            assert edges[1][0] - edges[0][0] == 8000, edges
            # Drift without resynchronization is explicitly limited in this study.
            assert abs(edges[0][0] - (start + ack_index * bit_ns)) <= 1600, edges
        else:
            assert edges == [], edges
        return start, bit_ns, sampled


async def setup(dut):
    assert os.environ.get("WAVE_C_CAPACITY_EXPERIMENT") == "can"
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    bus = Bus(dut)
    cocotb.start_soon(bus.resolve())
    await load_program(dut, candidate_words("can"))
    cocotb.start_soon(bus.sample_trace())
    return PinController(dut, 0x43414E), bus


async def receive(
    controller,
    bus,
    ident,
    identifier,
    data,
    *,
    status=0,
    crc_error=False,
    stuff_error=False,
    form_error=False,
    ppm=0,
    phase_ns=1,
    header_flags=(0, 0, 0),
    dlc=None,
):
    request = Request(ident, 1, output_limit=11)
    await controller.submit(request, b"")
    await Timer(110, unit="us")
    sample_start = len(bus.samples)
    wire, ack_index, stuffing = frame(
        identifier, data, crc_error=crc_error, header_flags=header_flags, dlc=dlc
    )
    if stuff_error:
        assert stuffing
        wire[stuffing[0]] ^= 1
    if form_error:
        wire[ack_index - 1] = 0
    sender = cocotb.start_soon(
        bus.send(wire, ack_index, ppm=ppm, phase_ns=phase_ns, acknowledge=status == 0)
    )
    output, event = await controller.complete(request, poll_limit=30000)
    timing = await sender
    assert event.status == status, event
    expected = (
        b"" if status else bytes([identifier >> 8, identifier & 255, len(data)]) + data
    )
    assert output == [(byte, 0) for byte in expected], (event, output, expected)
    assert bus.drive() == 1
    samples = bus.samples[sample_start:]
    assert len(samples) >= 2
    assert all(right - left == 8000 for left, right in pairwise(samples)), samples
    assert await controller.read(0x101) == 0
    return timing


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_can_receive_live_crc_ack(dut):
    controller, bus = await setup(dut)
    rng = random.Random(0x43414E)
    for ident, (identifier, data) in enumerate(
        [
            (0, b""),
            (0x7FF, b"\xff"),
            (0x123, bytes(8)),
            (0x555, b"\xff" * 8),
            (0x321, bytes(rng.randrange(256) for _ in range(8))),
        ]
    ):
        dut._log.info("CAN RX id=%03x data=%s", identifier, data.hex())
        await receive(controller, bus, ident, identifier, data)
    # Exercise all supported DLC values and the last-CRC-bit stuff boundary.
    for length in range(2, 8):
        await receive(
            controller,
            bus,
            length + 5,
            rng.randrange(2048),
            bytes(rng.randrange(256) for _ in range(length)),
        )
    for identifier in range(2048):
        _wire, ack_index, stuffing = frame(identifier, b"\xa5")
        if stuffing and stuffing[-1] == ack_index - 2:
            await receive(controller, bus, 15, identifier, b"\xa5")
            break
    else:
        raise AssertionError("No final-CRC stuff-bit vector found")


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_can_receive_fault_recovery(dut):
    controller, bus = await setup(dut)
    for ident, kwargs, status in [
        (20, {"crc_error": True}, 16),
        (21, {"stuff_error": True}, 19),
        (22, {"form_error": True}, 17),
        (23, {"header_flags": (1, 0, 0)}, 18),
        (24, {"header_flags": (0, 1, 0)}, 18),
        (25, {"dlc": 9}, 18),
        (26, {}, 0),
    ]:
        await receive(controller, bus, ident, 0, bytes(8), status=status, **kwargs)


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_can_receive_phase_frequency(dut):
    controller, bus = await setup(dut)
    ident = 100
    for phase_ns in [1, 5, 10, 15, 19]:
        for ppm in [-1000, 0, 1000]:
            await receive(
                controller,
                bus,
                ident,
                0x6A5,
                b"\x00\xff\x55\xaa\x01\x80\x00\xff",
                ppm=ppm,
                phase_ns=phase_ns,
            )
            ident += 1


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def test_can_receive_timeout(dut):
    controller, bus = await setup(dut)
    request = Request(200, 1, output_limit=11)
    await controller.submit(request, b"")
    output, event = await controller.complete(request, poll_limit=50000)
    assert event.status == 6 and output == [], event
    await receive(controller, bus, 201, 0x456, b"\x5a")
