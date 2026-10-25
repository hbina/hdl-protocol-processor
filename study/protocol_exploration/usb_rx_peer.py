"""USB packet oracle and TUSB1106 digital boundary; not an enumeration model."""

import json
import os
import random
from itertools import pairwise
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ValueChange
from cocotb.utils import get_sim_time
from run_usb_rx import candidate_words
from isa_variants import label_addresses

from test import PinController, load_program, reset
from tools.runtime import Request


def crc16(payload):
    # Polynomial long division, independently of firmware's reflected LFSR.
    sequence = [(byte >> bit) & 1 for byte in payload for bit in range(8)]
    value = 0
    for bit in sequence:
        value = value << 1 | bit
    dividend = (0xFFFF << len(sequence)) ^ (value << 16)
    while dividend.bit_length() > 16:
        dividend ^= 0x18005 << (dividend.bit_length() - 17)
    reflected = int(f"{dividend:016b}"[::-1], 2) ^ 0xFFFF
    return reflected.to_bytes(2, "little")


def encode(packet):
    line, ones = 2, 0
    states, stuff = [], []
    for byte in b"\x80" + packet:
        for bit in range(8):
            value = (byte >> bit) & 1
            if not value:
                line ^= 3
            states.append(line)
            ones = ones + 1 if value else 0
            if ones == 6:
                line ^= 3
                states.append(line)
                stuff.append(len(states) - 1)
                ones = 0
    return states + [0, 0, 2], stuff


class Transceiver:
    def __init__(self, dut):
        self.dut = dut
        self.host = None
        self.ack_start = None
        self.device_active = False
        self.device_transitions = []
        self.samples = []
        self.timings = []
        self.phases = {}

    def controls(self):
        oe, out = int(self.dut.uio_oe.value), int(self.dut.uio_out.value)
        assert not oe & ~0x3C, (oe, out)
        enabled = bool(oe & 0x10 and not out & 0x10)
        return enabled, (out >> 2) & 3, bool(oe & out & 0x20)

    async def resolve(self):
        last_device = None
        while True:
            enabled, driven, attached = self.controls()
            assert not (enabled and self.host is not None), (
                "USB drive ownership conflict"
            )
            if enabled and not self.device_active:
                self.ack_start = get_sim_time(unit="ps")
                self.device_transitions = []
            if enabled and driven != last_device:
                self.device_transitions.append((get_sim_time(unit="ps"), driven))
            self.device_active = enabled
            last_device = driven if enabled else None
            line = (
                driven
                if enabled
                else (self.host if self.host is not None else (2 if attached else 0))
            )
            self.dut.uio_in.value = line
            await Timer(10, unit="ns")

    async def trace_capture(self):
        variant = os.environ["WAVE_C_CAPACITY_EXPERIMENT"]
        source = Path(__file__).with_name(f"{variant}_candidate.asm").read_text()
        labels = label_addresses(source)
        addresses = {labels[f"capture_{index}"] for index in range(3)}
        stages = {labels[name]: name for name in ["decode", "crc_begin", "crc_done"]}
        core = self.dut.user_project.core
        while True:
            await ValueChange(core.pc)
            await Timer(1, unit="ps")
            address = int(core.pc.value)
            if address in addresses or address in stages:
                while int(core.wait_count.value):
                    await RisingEdge(self.dut.clk)
                    await Timer(1, unit="ps")
                await RisingEdge(self.dut.clk)
                if address in addresses:
                    self.samples.append(get_sim_time(unit="ns"))
                if address in stages:
                    self.phases[stages[address]] = get_sim_time(unit="ps")

    async def send(self, states, *, ppm=0, phase_ps=1):
        assert not self.device_active
        period = round(1_000_000_000_000 / 1_500_000 / (1 + ppm / 1_000_000))
        await Timer(phase_ps, unit="ps")
        start = get_sim_time(unit="ps")
        for state in states:
            self.host = state
            await Timer(period, unit="ps")
        self.host = None
        return start + (len(states) - 1) * period

    async def ack_waveform(self):
        for _ in range(50000):
            if self.device_active:
                break
            await Timer(20, unit="ns")
        else:
            raise AssertionError("No diagnostic ACK")
        start = self.ack_start
        expected, _stuff = encode(b"\xd2")
        assert not _stuff
        for index, state in enumerate(expected):
            sample_at = start + round((index + 0.5) * 1_000_000_000_000 / 1_500_000)
            now = get_sim_time(unit="ps")
            await Timer(sample_at - now, unit="ps")
            enabled, actual, _attached = self.controls()
            assert enabled and actual == state, (index, enabled, actual, state)
        await Timer(500, unit="ns")
        assert not self.controls()[0]
        # Device transitions must follow33/33/34 core-clock timing, independent
        # of packet data and of the host's frequency/phase.
        for when, _state in self.device_transitions:
            nominal = round((when - start) / (1_000_000_000_000 / 1_500_000))
            assert abs(when - start - nominal * 1_000_000_000_000 / 1_500_000) <= 20_000
        return start


async def setup(dut):
    variant = os.environ.get("WAVE_C_CAPACITY_EXPERIMENT")
    assert variant in {"usb_rx", "usb_rx_compact"}
    assert crc16(b"123456789").hex() == "c8b4"
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    phy = Transceiver(dut)
    cocotb.start_soon(phy.resolve())
    await load_program(dut, candidate_words(variant))
    cocotb.start_soon(phy.trace_capture())
    return PinController(dut, 0x555342), phy


async def receive(
    controller,
    phy,
    ident,
    payload,
    *,
    pid=0xC3,
    ack=False,
    status=0,
    states=None,
    packet=None,
    ppm=0,
    phase_ps=1,
):
    request = Request(ident, 1, arguments_length=1, output_limit=11)
    phy.ack_start = None
    phy.phases = {}
    await controller.submit(request, b"", bytes([int(ack)]))
    await Timer(10, unit="us")
    if packet is None:
        packet = bytes([pid]) + payload + crc16(payload)
    if states is None:
        states, _ = encode(packet)
    sample_start = len(phy.samples)
    sender = cocotb.start_soon(phy.send(states, ppm=ppm, phase_ps=phase_ps))
    watcher = cocotb.start_soon(phy.ack_waveform()) if ack and status == 0 else None
    output, event = await controller.complete(request, poll_limit=50000)
    eop_j = await sender
    ack_start = await watcher if watcher else None
    assert event.status == status, event
    assert output == ([] if status else [(byte, 0) for byte in packet]), (
        event,
        output,
        packet,
    )
    assert not phy.controls()[0]
    if not ack or status:
        assert phy.ack_start is None, "unexpected ACK on passive/bad packet"
    samples = phy.samples[sample_start:]
    # Capture kernels cycle34/33/33; stop as soon as SE0 is seen.
    for index, (left, right) in enumerate(pairwise(samples)):
        assert right - left == [680, 660, 660][index % 3], samples
    assert await controller.read(0x101) == 0
    if watcher:
        latency = ack_start - eop_j
        phy.timings.append(
            {
                "payload_bytes": len(payload),
                "eop_j_ps": eop_j,
                "ack_start_ps": ack_start,
                "ack_latency_ps": latency,
                "decode_start_ps": phy.phases["decode"],
                "crc_start_ps": phy.phases["crc_begin"],
                "crc_finish_ps": phy.phases["crc_done"],
                "decode_elapsed_ps": phy.phases["crc_begin"] - phy.phases["decode"],
                "crc_elapsed_ps": phy.phases["crc_done"] - phy.phases["crc_begin"],
            }
        )
        return latency
    return None


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_usb_packet_receive(dut):
    controller, phy = await setup(dut)
    rng = random.Random(0x555342)
    for length in range(9):
        await receive(
            controller,
            phy,
            length,
            bytes(rng.randrange(256) for _ in range(length)),
            pid=0xC3 if length % 2 else 0x4B,
        )
    await receive(controller, phy, 10, b"\xff" * 8)
    await receive(controller, phy, 11, bytes(8))


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_usb_packet_errors_recovery(dut):
    controller, phy = await setup(dut)
    packet = b"\xc3" + b"\xff" * 8 + crc16(b"\xff" * 8)
    await receive(
        controller,
        phy,
        20,
        b"\xff" * 8,
        packet=packet[:-1] + bytes([packet[-1] ^ 1]),
        status=16,
        ack=True,
    )
    await receive(
        controller,
        phy,
        21,
        b"\xff" * 8,
        packet=b"\xc2" + packet[1:],
        status=21,
        ack=True,
    )
    states, stuffing = encode(packet)
    bad_stuff = states.copy()
    bad_stuff[stuffing[0]] = bad_stuff[stuffing[0] - 1]
    await receive(
        controller, phy, 22, b"\xff" * 8, states=bad_stuff, status=19, ack=True
    )
    bad_sync = states.copy()
    bad_sync[2] = 2
    await receive(
        controller, phy, 23, b"\xff" * 8, states=bad_sync, status=17, ack=True
    )
    await receive(
        controller,
        phy,
        24,
        b"\xff" * 8,
        states=states[:-3] + [0, 2],
        status=17,
        ack=True,
    )
    bad_line = states.copy()
    bad_line[20] = 3
    await receive(
        controller, phy, 25, b"\xff" * 8, states=bad_line, status=17, ack=True
    )
    await receive(controller, phy, 26, bytes(9), status=20, ack=True)
    await receive(controller, phy, 27, b"", states=encode(b"")[0], status=17, ack=True)
    await receive(controller, phy, 28, b"\xa5\x5a")


@cocotb.test(timeout_time=40, timeout_unit="ms")
async def test_usb_packet_phase_frequency(dut):
    controller, phy = await setup(dut)
    ident = 100
    for phase in [1, 5000, 10000, 15000, 19999]:
        for ppm in [-1000, 0, 1000]:
            await receive(
                controller,
                phy,
                ident,
                b"\xff\x00\x55\xaa\x01\x80\x7f\xfe",
                phase_ps=phase,
                ppm=ppm,
            )
            ident += 1


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def test_usb_packet_diagnostic_ack(dut):
    controller, phy = await setup(dut)
    for ident, payload in enumerate([b"", b"\xa5", b"\xff" * 8], 200):
        phy.ack_start = None
        latency = await receive(controller, phy, ident, payload, ack=True)
        dut._log.info(
            "Buffered USB ACK latency: payload=%d, %.3f us",
            len(payload),
            latency / 1_000_000,
        )
    Path("ack_timings.json").write_text(json.dumps(phy.timings, indent=2) + "\n")


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_usb_packet_timeout(dut):
    controller, phy = await setup(dut)
    request = Request(250, 1, arguments_length=1, output_limit=11)
    await controller.submit(request, b"", b"\x00")
    output, event = await controller.complete(request, poll_limit=100000)
    assert output == [] and event.status == 6, event
    await receive(controller, phy, 251, b"\x42")
