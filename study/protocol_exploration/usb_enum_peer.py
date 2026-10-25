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

_DESCRIPTOR_DATA = json.loads(
    Path(__file__).with_name("usb_enum_constants.json").read_text()
)
IMAGE_DATA = bytes(_DESCRIPTOR_DATA["device"] + _DESCRIPTOR_DATA["configuration"])
# Independent host expectations; it never derives expected wire bytes from ROM.
EXPECTED_DEVICE = bytes.fromhex("1201100100000008addeefbe000100000001")
EXPECTED_CONFIG = bytes.fromhex("0902120001010080320904000000ff000000")


async def trace_control(phy):
    _, labels = base_assembler()._parse_lines(
        Path(__file__)
        .with_name(os.environ.get("USB_ENUM_CANDIDATE", "usb_enum_candidate.asm"))
        .read_text()
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
            "read_ack_done",
        ]
        if name in labels
    }
    core = phy.dut.user_project.core
    while True:
        await ValueChange(core.pc)
        await Timer(1, unit="ps")
        if int(core.pc.value) in chosen:
            phy.trace.append((int(get_sim_time(unit="ps")), chosen[int(core.pc.value)]))


async def setup(dut):
    assert os.environ.get("USB_ENUM_EXPERIMENT") == "1"
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    phy = Transceiver(dut)
    phy.address = 0
    phy.trace = deque(maxlen=100)
    phy.host_marks = deque(maxlen=10)
    cocotb.start_soon(phy.resolve())
    await load_program(
        dut,
        assemble(
            Path(__file__)
            .with_name(os.environ.get("USB_ENUM_CANDIDATE", "usb_enum_candidate.asm"))
            .read_text()
        ),
    )
    cocotb.start_soon(trace_control(phy))
    return PinController(dut, 0x455030), phy


async def out_packet(phy, payload, *, setup_packet=False, ppm=0, phase_ps=1):
    phy.ack_start = None
    phy.host_marks.append((int(get_sim_time(unit="ps")), "OUT", payload.hex()))
    pid = 0xC3 if setup_packet else 0x4B
    packets = [
        token(phy.address, 0, 0x2D if setup_packet else 0xE1),
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


async def in_packet(phy, payload, *, ack=True, ppm=0, phase_ps=1, pid=0x4B):
    phy.ack_start = None
    watcher = cocotb.start_soon(data_waveform(phy, payload, pid))
    endings = await send_packets(
        phy, [token(phy.address, 0, 0x69)], ppm=ppm, phase_ps=phase_ps
    )
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
    controller, phy, ident, payload, *, retries=False, ppm=0, phase_ps=1, request=None
):
    if request is None:
        request = Request(ident, 1, arguments_length=77, output_limit=len(payload))
        await controller.submit(
            request, b"", bytes([1, *CONSTANTS, 0, 0, 0x4B, 0]) + IMAGE_DATA
        )
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
    request = Request(200, 1, arguments_length=77, output_limit=8)
    await controller.submit(
        request, b"", bytes([1, *CONSTANTS, 0, 0, 0x4B, 0]) + IMAGE_DATA
    )
    await Timer(10, unit="us")
    await out_packet(phy, bytes([0x40, 1, 0, 0, 0, 0, 8, 0]), setup_packet=True)
    await gap(phy, 0)
    phy.ack_start = None
    payload = bytes(range(8))
    check = crc16(payload)
    packets = [
        token(phy.address, 0),
        b"\x4b" + payload + check[:-1] + bytes([check[-1] ^ 1]),
    ]
    await send_packets(phy, packets)
    output, event = await controller.complete(request, poll_limit=100000)
    assert output == [] and event.status == 16, event
    assert phy.ack_start is None
    await control_pair(controller, phy, 201, b"\xf9\xa5\x5a")


async def quiet_in(phy, address):
    phy.ack_start = None
    await send_packets(phy, [token(address, 0, 0x69)])
    await Timer(10, unit="us")
    assert phy.ack_start is None, ("unexpected address response", address)


async def set_address(phy, address, *, retry=False, ppm=0, phase_ps=1):
    old = phy.address
    await out_packet(
        phy,
        bytes([0, 5, address, 0, 0, 0, 0, 0]),
        setup_packet=True,
        ppm=ppm,
        phase_ps=phase_ps,
    )
    await gap(phy, 0)
    await quiet_in(phy, address)  # Pending address must not respond yet.
    if retry:
        await in_packet(phy, b"", ack=False, ppm=ppm, phase_ps=phase_ps)
        await gap(phy, ppm)
        await quiet_in(phy, address)
    await in_packet(
        phy, b"", ppm=ppm, phase_ps=phase_ps
    )  # Status is still addressed to the old address.
    await gap(phy, 0)
    phy.address = address
    await quiet_in(phy, old)


async def bus_reset(phy, *, duration_us=10000, recovery_us=10000):
    assert not phy.controls()[0]
    phy.ack_start = None
    phy.host = 0
    await Timer(duration_us, unit="us")
    phy.host = None
    phy.address = 0
    await Timer(recovery_us, unit="us")
    assert phy.ack_start is None, "device drove during bus reset/recovery"


@cocotb.test(timeout_time=60, timeout_unit="ms")
async def test_set_address_deferred_commit_and_bus_reset(dut):
    controller, phy = await setup(dut)
    request = Request(300, 1, arguments_length=77, output_limit=8)
    await controller.submit(
        request, b"", bytes([1, *CONSTANTS, 0, 0, 0x4B, 0]) + IMAGE_DATA
    )
    await Timer(10, unit="us")
    await set_address(phy, 37, retry=True)
    # A real10ms reset and10ms recovery must not expire the runtime service.
    await bus_reset(phy)
    await quiet_in(phy, 37)
    await set_address(phy, 127, retry=True)
    await control_pair(
        controller, phy, 300, b"\xff\x00\x55\xaa\x01\x80\x7f\xfe", request=request
    )
    Path("address_timings.json").write_text(json.dumps(phy.timings, indent=2) + "\n")


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def test_reset_aborts_pending_address_and_partial_packet(dut):
    controller, phy = await setup(dut)
    request = Request(301, 1, arguments_length=77, output_limit=3)
    await controller.submit(
        request, b"", bytes([1, *CONSTANTS, 0, 0, 0x4B, 0]) + IMAGE_DATA
    )
    await Timer(10, unit="us")
    await out_packet(phy, bytes([0, 5, 37, 0, 0, 0, 0, 0]), setup_packet=True)
    await gap(phy, 0)
    await in_packet(phy, b"", ack=False)
    await gap(phy, 0)
    # Short SE0 does not meet the reset qualification time.
    phy.host = 0
    await Timer(1200, unit="ns")
    phy.host = None
    await Timer(3, unit="us")
    await in_packet(phy, b"")
    await gap(phy, 0)
    phy.address = 37
    await quiet_in(phy, 0)
    # Filter-duration test, separate from the full10ms reset above.
    await bus_reset(phy, duration_us=20, recovery_us=10)
    await quiet_in(phy, 37)
    await out_packet(phy, bytes([0, 5, 1, 0, 0, 0, 0, 0]), setup_packet=True)
    await gap(phy, 0)
    await in_packet(phy, b"", ack=False)
    await gap(phy, 0)
    await bus_reset(phy, duration_us=20, recovery_us=10)
    await quiet_in(phy, 1)
    # Abort an unfinished incoming packet without touching rst_n or loader.
    states, _ = encode(b"\xc3\x40\x01")
    await phy.send(states[:12])
    await bus_reset(phy, duration_us=20, recovery_us=10)
    await control_pair(controller, phy, 301, b"\xf9\xa5\x5a", request=request)


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_address_phase_rate_and_vendor_readback(dut):
    controller, phy = await setup(dut)
    ident = 400
    for address in [1, 37, 127]:
        for phase, ppm in [(1, -1000), (10000, 0), (19999, 1000)]:
            phy.address = 0
            request = Request(ident, 1, arguments_length=77, output_limit=8)
            await controller.submit(
                request, b"", bytes([1, *CONSTANTS, 0, 0, 0x4B, 0]) + IMAGE_DATA
            )
            await Timer(10, unit="us")
            await set_address(phy, address, ppm=ppm, phase_ps=phase)
            await control_pair(
                controller,
                phy,
                ident,
                b"\xff\x00\x55\xaa\x01\x80\x7f\xfe",
                request=request,
                ppm=ppm,
                phase_ps=phase,
            )
            ident += 1
    Path("address_phase_timings.json").write_text(
        json.dumps(phy.timings, indent=2) + "\n"
    )


async def standard_read(
    phy,
    request,
    expected,
    *,
    retry=False,
    index=0,
    length=None,
    minimum_gap=False,
    ppm=0,
    phase_ps=1,
):
    if length is None:
        length = len(expected)
    setup_bytes = bytes(
        [
            0x80,
            request,
            index,
            1 if request == 6 else 0,
            0,
            0,
            length & 255,
            length >> 8,
        ]
    )
    # Descriptor type2 selects the configuration; GET_CONFIGURATION has value0.
    if index == 2:
        setup_bytes = bytes([0x80, 6, 0, 2, 0, 0, length & 255, length >> 8])
    await out_packet(phy, setup_bytes, setup_packet=True, ppm=ppm, phase_ps=phase_ps)
    await gap(phy, ppm)
    for offset in range(0, len(expected), 8):
        pid = 0x4B if offset % 16 == 0 else 0xC3
        if retry:
            await in_packet(
                phy,
                expected[offset : offset + 8],
                ack=False,
                pid=pid,
                ppm=ppm,
                phase_ps=phase_ps,
            )
            await Timer(3, unit="us")
        await in_packet(
            phy, expected[offset : offset + 8], pid=pid, ppm=ppm, phase_ps=phase_ps
        )
        if minimum_gap:
            await gap(phy, ppm)
        else:
            await Timer(3, unit="us")
    await out_packet(phy, b"", ppm=ppm, phase_ps=phase_ps)
    await gap(phy, ppm)


async def set_configuration(phy, value, *, retry=False):
    await out_packet(phy, bytes([0, 9, value, 0, 0, 0, 0, 0]), setup_packet=True)
    await gap(phy, 0)
    if retry:
        await in_packet(phy, b"", ack=False)
        await Timer(3, unit="us")
    await in_packet(phy, b"")
    await Timer(3, unit="us")


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_descriptor_chunks_and_configuration(dut):
    controller, phy = await setup(dut)
    request = Request(500, 1, arguments_length=77, output_limit=8)
    await controller.submit(
        request, b"", bytes([1, *CONSTANTS, 0, 0, 0x4B, 0]) + IMAGE_DATA
    )
    await Timer(10, unit="us")
    await standard_read(phy, 6, EXPECTED_DEVICE[:8], length=8)
    await standard_read(phy, 6, EXPECTED_DEVICE, length=255, retry=True)
    await standard_read(phy, 6, EXPECTED_CONFIG, index=2, length=18)
    await standard_read(phy, 8, b"\x00")
    await set_configuration(phy, 1, retry=True)
    await standard_read(phy, 8, b"\x01")
    await set_configuration(phy, 0)
    await standard_read(phy, 8, b"\x00")
    await control_pair(controller, phy, 500, bytes(range(8)), request=request)
    Path("descriptor_timings.json").write_text(json.dumps(phy.timings, indent=2) + "\n")


@cocotb.test(timeout_time=60, timeout_unit="ms")
async def test_enumeration_and_vendor_transfer(dut):
    controller, phy = await setup(dut)
    request = Request(501, 1, arguments_length=77, output_limit=8)
    await controller.submit(
        request, b"", bytes([1, *CONSTANTS, 0, 0, 0x4B, 0]) + IMAGE_DATA
    )
    await Timer(10, unit="us")
    await bus_reset(phy)
    await standard_read(phy, 6, EXPECTED_DEVICE[:8], length=8)
    assert EXPECTED_DEVICE[7] == 8
    await set_address(phy, 37, retry=True)
    await standard_read(phy, 6, EXPECTED_DEVICE, length=18, retry=True)
    await standard_read(phy, 6, EXPECTED_CONFIG[:9], index=2, length=9)
    total = int.from_bytes(EXPECTED_CONFIG[2:4], "little")
    assert total == len(EXPECTED_CONFIG) and EXPECTED_CONFIG[5] == 1
    await standard_read(phy, 6, EXPECTED_CONFIG, index=2, length=total, retry=True)
    await set_configuration(phy, 1, retry=True)
    await standard_read(phy, 8, b"\x01")
    await control_pair(
        controller, phy, 501, b"\xff\x00\x55\xaa\x01\x80\x7f\xfe", request=request
    )
    Path("enumeration_timings.json").write_text(
        json.dumps(phy.timings, indent=2) + "\n"
    )


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def test_descriptor_short_interpacket_gap(dut):
    controller, phy = await setup(dut)
    request = Request(502, 1, arguments_length=77, output_limit=3)
    await controller.submit(
        request, b"", bytes([1, *CONSTANTS, 0, 0, 0x4B, 0]) + IMAGE_DATA
    )
    await Timer(10, unit="us")
    await standard_read(phy, 6, EXPECTED_DEVICE, minimum_gap=True)
    await standard_read(phy, 6, EXPECTED_CONFIG, index=2, minimum_gap=True)
    await control_pair(controller, phy, 502, b"\xf9\xa5\x5a", request=request)


@cocotb.test(timeout_time=40, timeout_unit="ms")
async def test_descriptor_phase_rate_and_configuration_commit(dut):
    controller, phy = await setup(dut)
    ident = 600
    for phase in [1, 10000, 19999]:
        for ppm in [-1000, 0, 1000]:
            request = Request(ident, 1, arguments_length=77, output_limit=3)
            await controller.submit(
                request, b"", bytes([1, *CONSTANTS, 0, 0, 0x4B, 0]) + IMAGE_DATA
            )
            await Timer(10, unit="us")
            await standard_read(
                phy,
                6,
                EXPECTED_DEVICE,
                minimum_gap=True,
                retry=True,
                ppm=ppm,
                phase_ps=phase,
            )
            await standard_read(
                phy,
                6,
                EXPECTED_CONFIG,
                index=2,
                minimum_gap=True,
                ppm=ppm,
                phase_ps=phase,
            )
            if ppm == 0 and phase == 1:
                # A new SETUP aborts a status stage that was never ACKed.
                await out_packet(
                    phy, bytes([0, 9, 1, 0, 0, 0, 0, 0]), setup_packet=True
                )
                await gap(phy, 0)
                await in_packet(phy, b"", ack=False)
                await Timer(3, unit="us")
                await standard_read(phy, 8, b"\x00")
                await set_configuration(phy, 1, retry=True)
                await standard_read(phy, 8, b"\x01")
                await bus_reset(phy, duration_us=20, recovery_us=10)
                await standard_read(phy, 8, b"\x00")
            await control_pair(controller, phy, ident, b"\xf9\xa5\x5a", request=request)
            ident += 1
    Path("descriptor_phase_timings.json").write_text(
        json.dumps(phy.timings, indent=2) + "\n"
    )
