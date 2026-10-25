"""Autonomous vendor EP0 write/status/read/status with independent wire host."""

import json
import os
import random
from collections import deque
from itertools import pairwise
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer, ValueChange
from cocotb.utils import get_sim_time
from generic_carry_frontier import assemble
from generic_frontier import base_assembler
from usb_rx_peer import Transceiver, crc16, encode
from usb_stream_peer import CONSTANTS, data_waveform, send_packets, token

from test import PinController, load_program, reset
from tools.runtime import Request


async def trace_control(phy):
    _, labels = base_assembler()._parse_lines(
        Path(__file__).with_name("usb_control_candidate.asm").read_text()
    )
    chosen = {
        labels[name]: name
        for name in [
            "rearm",
            "wait_idle",
            "wait_sop",
            "packet_start",
            "length_ok",
            "form_error",
            "ack_read_data",
        ]
    }
    core = phy.dut.user_project.core
    while True:
        await ValueChange(core.pc)
        await Timer(1, unit="ps")
        if int(core.pc.value) in chosen:
            phy.trace.append((int(get_sim_time(unit="ps")), chosen[int(core.pc.value)]))


async def setup(dut):
    assert os.environ.get("USB_CONTROL_EXPERIMENT") == "1"
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    phy = Transceiver(dut)
    phy.trace = deque(maxlen=100)
    phy.host_marks = deque(maxlen=10)
    cocotb.start_soon(phy.resolve())
    await load_program(
        dut, assemble(Path(__file__).with_name("usb_control_candidate.asm").read_text())
    )
    cocotb.start_soon(trace_control(phy))
    return PinController(dut, 0x455030), phy


async def out_packet(phy, payload, *, setup_packet=False, ppm=0, phase_ps=1):
    phy.ack_start = None
    phy.host_marks.append((int(get_sim_time(unit="ps")), "OUT", payload.hex()))
    pid = 0xC3 if setup_packet else 0x4B
    packets = [
        token(0, 0, 0x2D if setup_packet else 0xE1),
        bytes([pid]) + payload + crc16(payload),
    ]
    watcher = cocotb.start_soon(phy.ack_waveform())
    endings = await send_packets(phy, packets, ppm=ppm, phase_ps=phase_ps)
    try:
        start = await watcher
    except AssertionError as error:
        core = phy.dut.user_project.core
        raise AssertionError(
            (
                ppm,
                phase_ps,
                payload.hex(),
                int(core.pc.value),
                int(phy.dut.user_project.store.memory[171].value),
                [int(core.registers[i].value) for i in range(8)],
                phy.timings[-6:],
                list(phy.trace),
                list(phy.host_marks),
            )
        ) from error
    transitions = phy.device_transitions
    phy.last_eop_j = next(
        when
        for (previous, old), (when, new) in reversed(list(pairwise(transitions)))
        if old == 0 and new == 2
    )
    latency = start - endings[-1]
    assert 2e12 / 1.5e6 <= latency <= 6.5e12 / 1.5e6, latency
    phy.timings.append(
        {
            "stage": "SETUP" if setup_packet else "OUT",
            "bytes": len(payload),
            "ppm": ppm,
            "phase_ps": phase_ps,
            "response_latency_ps": latency,
        }
    )


async def in_packet(phy, payload, *, ack=True, ppm=0, phase_ps=1):
    phy.ack_start = None
    watcher = cocotb.start_soon(data_waveform(phy, payload, 0x4B))
    endings = await send_packets(phy, [token(0, 0, 0x69)], ppm=ppm, phase_ps=phase_ps)
    start, end_j, _stuff = await watcher
    latency = start - endings[0]
    assert 2e12 / 1.5e6 <= latency <= 6.5e12 / 1.5e6, latency
    phy.timings.append(
        {
            "stage": "IN",
            "bytes": len(payload),
            "ppm": ppm,
            "phase_ps": phase_ps,
            "response_latency_ps": latency,
        }
    )
    if ack:
        at = end_j + round(2e12 / 1.5e6)
        await Timer(at - int(get_sim_time(unit="ps")), unit="ps")
        states, _ = encode(b"\xd2")
        phy.host_marks.append((int(get_sim_time(unit="ps")), "ACK"))
        end_j = await phy.send(states, ppm=ppm, phase_ps=phase_ps)
    phy.last_eop_j = end_j


async def gap(phy, ppm):
    # Slightly above the two-bit minimum, covering digital resolver quantization.
    target = phy.last_eop_j + round(2.1e12 / 1.5e6 / (1 + ppm / 1e6))
    await Timer(target - int(get_sim_time(unit="ps")), unit="ps")


async def control_pair(
    controller, phy, ident, payload, *, retries=False, ppm=0, phase_ps=1
):
    request = Request(ident, 1, arguments_length=41, output_limit=len(payload))
    await controller.submit(request, b"", bytes([1, *CONSTANTS, 0, 0, 0x4B, 0]))
    await Timer(10, unit="us")
    # From this point until the final status ACK the runtime host takes no
    # action. Only the independent USB host drives the protocol wires.
    await out_packet(
        phy,
        bytes([0x40, 1, 0, 0, 0, 0, len(payload), 0]),
        setup_packet=True,
        ppm=ppm,
        phase_ps=phase_ps,
    )
    await gap(phy, ppm)
    await out_packet(phy, payload, ppm=ppm, phase_ps=phase_ps)
    await gap(phy, ppm)
    if retries:
        await out_packet(phy, payload, ppm=ppm, phase_ps=phase_ps)
        await gap(phy, ppm)
        await in_packet(phy, b"", ack=False, ppm=ppm, phase_ps=phase_ps)
        await gap(phy, ppm)
    await in_packet(phy, b"", ppm=ppm, phase_ps=phase_ps)
    await gap(phy, ppm)
    await out_packet(
        phy,
        bytes([0xC0, 2, 0, 0, 0, 0, len(payload), 0]),
        setup_packet=True,
        ppm=ppm,
        phase_ps=phase_ps,
    )
    await gap(phy, ppm)
    if retries:
        await in_packet(phy, payload, ack=False, ppm=ppm, phase_ps=phase_ps)
        await gap(phy, ppm)
    await in_packet(phy, payload, ppm=ppm, phase_ps=phase_ps)
    await gap(phy, ppm)
    await out_packet(phy, b"", ppm=ppm, phase_ps=phase_ps)
    output, event = await controller.complete(request, poll_limit=100000)
    assert event.status == 0 and event.input_consumed == 0, event
    assert event.output_produced == len(payload) and output == [(b, 0) for b in payload]
    assert await controller.read(0x101) == 0


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_autonomous_control_write_read(dut):
    controller, phy = await setup(dut)
    rng = random.Random(0x455030)
    for length in [1, 2, 7, 8]:
        await control_pair(
            controller, phy, length, bytes(rng.randrange(256) for _ in range(length))
        )
    await control_pair(controller, phy, 10, b"\xff" * 8, retries=True)
    await control_pair(controller, phy, 11, bytes(8), retries=True)
    Path("control_timings.json").write_text(json.dumps(phy.timings, indent=2) + "\n")


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_autonomous_control_phase_rate(dut):
    controller, phy = await setup(dut)
    ident = 100
    for phase in [1, 10000, 19999]:
        for ppm in [-1000, 0, 1000]:
            await control_pair(
                controller,
                phy,
                ident,
                b"\xff\x00\x55\xaa\x01\x80\x7f\xfe",
                ppm=ppm,
                phase_ps=phase,
            )
            ident += 1
    Path("control_phase_timings.json").write_text(
        json.dumps(phy.timings, indent=2) + "\n"
    )


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def test_control_crc_error_and_runtime_recovery(dut):
    controller, phy = await setup(dut)
    request = Request(200, 1, arguments_length=41, output_limit=8)
    await controller.submit(request, b"", bytes([1, *CONSTANTS, 0, 0, 0x4B, 0]))
    await Timer(10, unit="us")
    await out_packet(phy, bytes([0x40, 1, 0, 0, 0, 0, 8, 0]), setup_packet=True)
    await gap(phy, 0)
    phy.ack_start = None
    payload = bytes(range(8))
    check = crc16(payload)
    packets = [token(0, 0), b"\x4b" + payload + check[:-1] + bytes([check[-1] ^ 1])]
    await send_packets(phy, packets)
    output, event = await controller.complete(request, poll_limit=100000)
    assert output == [] and event.status == 16, event
    assert phy.ack_start is None
    await control_pair(controller, phy, 201, b"\xf9\xa5\x5a")
