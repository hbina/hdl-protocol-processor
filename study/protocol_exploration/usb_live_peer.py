"""Independent USB packet, CRC, waveform and response-deadline checks."""

import json
import os
import random
from itertools import pairwise
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ValueChange
from cocotb.utils import get_sim_time
from generic_call_frontier import assemble
from isa_variants import label_addresses
from usb_rx_peer import Transceiver, crc16, encode

from test import PinController, load_program, reset
from tools.isa import ADDI, CALL, CALL_FRONTIER, HALT, JMP, LDI, MOV, RET, r0, r4
from tools.program import place
from tools.runtime import Request

CONSTANTS = json.loads(Path(__file__).with_name("usb_live_constants.json").read_text())[
    "syndrome_table"
]


def final_stuff_vector():
    for value in range(256):
        payload = bytes([value])
        states, stuffing = encode(b"\xc3" + payload + crc16(payload))
        if stuffing and stuffing[-1] == len(states) - 4:
            return payload, states
    raise AssertionError("No final CRC stuff-bit vector")


async def trace_live(dut, phy):
    source = Path(__file__).with_name("usb_live_candidate.asm").read_text()
    labels = label_addresses(source)
    addresses = {
        labels[f"bit_{bit}_{phase}"]: phase for bit in range(8) for phase in range(3)
    }
    core = dut.user_project.core
    while True:
        await ValueChange(core.pc)
        await Timer(1, unit="ps")
        address = int(core.pc.value)
        if address in addresses:
            while int(core.wait_count.value):
                await RisingEdge(dut.clk)
                await Timer(1, unit="ps")
            await RisingEdge(dut.clk)
            phy.samples.append((get_sim_time(unit="ns"), addresses[address]))


async def setup(dut):
    assert os.environ.get("USB_LIVE_EXPERIMENT") == "1"
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    phy = Transceiver(dut)
    cocotb.start_soon(phy.resolve())
    await load_program(
        dut, assemble(Path(__file__).with_name("usb_live_candidate.asm").read_text())
    )
    cocotb.start_soon(trace_live(dut, phy))
    return PinController(dut, 0x4C4956), phy


async def receive(
    controller,
    phy,
    ident,
    payload,
    *,
    pid=0xC3,
    status=0,
    ack=True,
    states=None,
    packet=None,
    phase_ps=1,
    ppm=0,
):
    request = Request(ident, 1, arguments_length=37, output_limit=11)
    phy.ack_start = None
    # Static firmware constants, identical for all payloads and both PIDs.
    await controller.submit(request, b"", bytes([int(ack), *CONSTANTS]))
    await Timer(10, unit="us")
    if packet is None:
        packet = bytes([pid]) + payload + crc16(payload)
    if states is None:
        states, _stuff = encode(packet)
    trace_start = len(phy.samples)
    sender = cocotb.start_soon(phy.send(states, ppm=ppm, phase_ps=phase_ps))
    watcher = cocotb.start_soon(phy.ack_waveform()) if ack and status == 0 else None
    output, event = await controller.complete(request, poll_limit=50000)
    eop_j = await sender
    ack_start = await watcher if watcher else None
    assert event.status == status, event
    expected = [] if status else [(byte, 0) for byte in packet]
    assert output == expected, (event, output, expected)
    assert event.input_consumed == 0 and event.output_produced == len(expected)
    assert await controller.read(0x101) == 0
    samples = phy.samples[trace_start:]
    for (before, phase), (after, following_phase) in pairwise(samples):
        assert after - before == [660, 660, 680][phase], samples
        assert following_phase == (phase + 1) % 3
    if status == 0:
        assert len(samples) >= 25
    if watcher:
        latency = ack_start - eop_j
        minimum = 2 * 1_000_000_000_000 / 1_500_000
        maximum = 6.5 * 1_000_000_000_000 / 1_500_000
        assert minimum <= latency <= maximum, (
            f"USB response {latency / 1e6:.3f}us outside [{minimum / 1e6:.3f},{maximum / 1e6:.3f}]us"
        )
        phy.timings.append(
            {
                "pid": pid,
                "payload_bytes": len(payload),
                "host_phase_ps": phase_ps,
                "host_relative_ppm": ppm,
                "ack_latency_ps": latency,
            }
        )
        return latency
    assert phy.ack_start is None, "ACK on passive or malformed packet"
    return None


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def test_live_usb_data_and_deadline(dut):
    controller, phy = await setup(dut)
    rng = random.Random(0x555342)
    for length in range(9):
        payload = bytes(rng.randrange(256) for _ in range(length))
        for pid in [0xC3, 0x4B]:
            await receive(controller, phy, length * 2 + (pid == 0x4B), payload, pid=pid)
    await receive(controller, phy, 30, bytes(8))
    await receive(controller, phy, 31, b"\xff" * 8)
    payload, states = final_stuff_vector()
    await receive(controller, phy, 32, payload, states=states)
    await receive(controller, phy, 33, b"\xa5", ack=False)
    Path("live_timings.json").write_text(json.dumps(phy.timings, indent=2) + "\n")


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def test_live_usb_malformed_and_recovery(dut):
    controller, phy = await setup(dut)
    payload = b"\xff" * 8
    packet = b"\xc3" + payload + crc16(payload)
    await receive(
        controller,
        phy,
        40,
        payload,
        packet=packet[:-1] + bytes([packet[-1] ^ 1]),
        status=16,
    )
    await receive(controller, phy, 41, payload, packet=b"\xc2" + packet[1:], status=21)
    states, stuffing = encode(packet)
    bad = states.copy()
    bad[stuffing[0]] = bad[stuffing[0] - 1]
    await receive(controller, phy, 42, payload, states=bad, status=19)
    bad = states.copy()
    bad[20] = 3
    await receive(controller, phy, 43, payload, states=bad, status=17)
    await receive(controller, phy, 44, payload, states=states[:-3] + [0, 2], status=17)
    await receive(controller, phy, 45, bytes(9), status=20)
    await receive(controller, phy, 46, b"", states=encode(b"")[0], status=17)
    await receive(controller, phy, 47, b"\x5a\xa5")
    payload, states = final_stuff_vector()
    await receive(
        controller, phy, 48, payload, states=states[:-4] + states[-3:], status=19
    )
    await receive(controller, phy, 49, b"\xa5", pid=0x87, status=18)
    states, _ = encode(packet)
    states[2] = 2
    await receive(controller, phy, 50, b"\xff" * 8, states=states, status=17)
    await receive(controller, phy, 51, b"\x42")


@cocotb.test(timeout_time=25, timeout_unit="ms")
async def test_live_usb_phase_frequency_deadline(dut):
    controller, phy = await setup(dut)
    ident = 100
    for phase in [1, 5000, 10000, 15000, 19999]:
        for ppm in [-1000, 0, 1000]:
            await receive(
                controller,
                phy,
                ident,
                b"\xff\x00\x55\xaa\x01\x80\x7f\xfe",
                pid=0x4B,
                phase_ps=phase,
                ppm=ppm,
            )
            ident += 1
    Path("live_phase_timings.json").write_text(json.dumps(phy.timings, indent=2) + "\n")


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def test_live_usb_timeout_recovery(dut):
    controller, phy = await setup(dut)
    request = Request(200, 1, arguments_length=37, output_limit=11)
    await controller.submit(request, b"", bytes([0, *CONSTANTS]))
    output, event = await controller.complete(request, poll_limit=100000)
    assert output == [] and event.status == 6, event
    await receive(controller, phy, 201, b"\x42")


@cocotb.test(timeout_time=5, timeout_unit="ms")
async def test_generic_call_return_banks(dut):
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut)
    image = place(
        {
            0: LDI(r4, 1),
            1: CALL(900),
            2: JMP(510),
            510: CALL(768),
            511: MOV(r0, r4),
            512: HALT(),
            768: ADDI(r4, 4),
            769: RET(),
            900: ADDI(r4, 2),
            901: RET(),
        },
        1024,
    )
    await load_program(dut, image.link(CALL_FRONTIER).words)
    await Timer(2, unit="us")
    dut.ena.value = 0
    assert await PinController(dut).read(0x10B) == 7
    await load_program(dut, assemble("HALT"))
    assert int(dut.user_project.core.return_pc.value) == 0
