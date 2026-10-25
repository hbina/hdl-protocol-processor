"""Independent USB token/data host for the addressed OUT/SETUP probe."""

import json
import os
import random
from itertools import pairwise
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ValueChange
from cocotb.utils import get_sim_time
from generic_carry_frontier import assemble
from generic_frontier import base_assembler
from usb_rx_peer import Transceiver, crc16, encode

from test import PinController, load_program, reset
from tools.runtime import Request

CONSTANTS = json.loads(Path(__file__).with_name("usb_live_constants.json").read_text())[
    "syndrome_table"
]


def token(address, endpoint, pid=0xE1):
    # Independent polynomial division, not the firmware's reflected bit loop.
    bits = [(address >> bit) & 1 for bit in range(7)] + [
        (endpoint >> bit) & 1 for bit in range(4)
    ]
    value = 0
    for bit in bits:
        value = value << 1 | bit
    remainder = (31 << 11) ^ (value << 5)
    while remainder.bit_length() > 5:
        remainder ^= 0x25 << (remainder.bit_length() - 6)
    check = int(f"{remainder:05b}"[::-1], 2) ^ 31
    return bytes([pid]) + (address | endpoint << 7 | check << 11).to_bytes(2, "little")


async def trace_packets(dut, phy):
    source = Path(__file__).with_name("usb_stream_candidate.asm").read_text()
    _, labels = base_assembler()._parse_lines(source)
    samples = {labels[f"sample_{phase}"]: phase for phase in range(3)}
    core = dut.user_project.core
    group = None
    while True:
        await ValueChange(core.pc)
        await Timer(1, unit="ps")
        address = int(core.pc.value)
        if address == labels["packet_start"]:
            group = []
            phy.packet_samples.append(group)
        elif address in samples:
            while int(core.wait_count.value):
                await RisingEdge(dut.clk)
                await Timer(1, unit="ps")
            await RisingEdge(dut.clk)
            assert group is not None
            group.append((int(get_sim_time(unit="ps")), samples[address]))


async def setup(dut):
    assert os.environ.get("USB_STREAM_EXPERIMENT") == "1"
    assert token(0, 0, 0x2D) == b"\x2d\x00\x10"
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    phy = Transceiver(dut)
    phy.packet_samples = []
    cocotb.start_soon(phy.resolve())
    await load_program(
        dut, assemble(Path(__file__).with_name("usb_stream_candidate.asm").read_text())
    )
    cocotb.start_soon(trace_packets(dut, phy))
    return PinController(dut, 0x4F5554), phy


async def send_packets(phy, packets, *, ppm=0, phase_ps=1, gap_bits=2):
    period = round(1e12 / 1.5e6 / (1 + ppm / 1e6))
    endings = []
    for index, packet in enumerate(packets):
        if index:
            # send() already drove one J bit after SE0; USB's gap is measured
            # from the preceding SE0->J edge, so wait only the remaining gap.
            await Timer(round((gap_bits - 1) * period), unit="ps")
        states, _ = encode(packet)
        endings.append(await phy.send(states, ppm=ppm, phase_ps=phase_ps))
    return endings


async def transact(
    controller,
    phy,
    ident,
    payload,
    *,
    address=0,
    endpoint=0,
    pid=0xC3,
    token_pid=0xE1,
    prefix=None,
    packets=None,
    status=0,
    ppm=0,
    phase_ps=1,
    gap_bits=2,
):
    request = Request(ident, 1, arguments_length=41, output_limit=11)
    phy.ack_start = None
    await controller.submit(
        request, b"", bytes([1, *CONSTANTS, address, endpoint, 0xC3, 0])
    )
    await Timer(10, unit="us")
    data = bytes([pid]) + payload + crc16(payload)
    if packets is None:
        packets = list(prefix or []) + [token(address, endpoint, token_pid), data]
    trace_start = len(phy.packet_samples)
    sender = cocotb.start_soon(
        send_packets(phy, packets, ppm=ppm, phase_ps=phase_ps, gap_bits=gap_bits)
    )
    watcher = cocotb.start_soon(phy.ack_waveform()) if status == 0 else None
    output, event = await controller.complete(request, poll_limit=100000)
    endings = await sender
    ack = await watcher if watcher else None
    assert event.status == status, event
    expected = [] if status else [(byte, 0) for byte in data]
    assert output == expected, (event, output, expected)
    assert event.input_consumed == 0 and event.output_produced == len(expected)
    assert await controller.read(0x101) == 0
    for group in phy.packet_samples[trace_start:]:
        for (before, phase), (after, following) in pairwise(group):
            assert after - before == [660000, 660000, 680000][phase], group
            assert following == (phase + 1) % 3
    if status == 0:
        assert event.detail == token_pid, event
        latency = ack - endings[-1]
        assert 2e12 / 1.5e6 <= latency <= 6.5e12 / 1.5e6, latency
        phy.timings.append(
            {
                "address": address,
                "endpoint": endpoint,
                "token_pid": token_pid,
                "data_pid": pid,
                "payload_bytes": len(payload),
                "gap_bits": gap_bits,
                "relative_ppm": ppm,
                "phase_ps": phase_ps,
                "ack_latency_ps": latency,
            }
        )
    else:
        assert phy.ack_start is None, "ACK for rejected transaction"


@cocotb.test(timeout_time=25, timeout_unit="ms")
async def test_addressed_out_setup(dut):
    controller, phy = await setup(dut)
    rng = random.Random(0x43524335)
    for length in range(9):
        address, endpoint = [(0, 0), (1, 1), (37, 7), (127, 15)][length % 4]
        await transact(
            controller,
            phy,
            length,
            bytes(rng.randrange(256) for _ in range(length)),
            address=address,
            endpoint=endpoint,
            pid=0xC3 if length % 2 else 0x4B,
        )
    await transact(
        controller, phy, 10, b"\x80\x06\x00\x01\x00\x00\x12\x00", token_pid=0x2D
    )
    Path("out_timings.json").write_text(json.dumps(phy.timings, indent=2) + "\n")


@cocotb.test(timeout_time=25, timeout_unit="ms")
async def test_token_filter_crc5_and_orphan_data(dut):
    controller, phy = await setup(dut)
    data = b"\xc3\xa5" + crc16(b"\xa5")
    bad = bytearray(token(37, 7))
    bad[2] ^= 8
    prefix = [token(36, 7), data, token(37, 6), data, bytes(bad), data, data]
    await transact(
        controller, phy, 20, b"\x5a\xa5", address=37, endpoint=7, prefix=prefix
    )
    # Intervening IN invalidates an earlier OUT gate; orphan DATA stays silent.
    prefix = [token(37, 7), token(37, 7, 0x69), data]
    await transact(controller, phy, 21, b"\x42", address=37, endpoint=7, prefix=prefix)
    # Each of the five CRC5 bits is independently corrupted.
    prefix = []
    for bit in range(3, 8):
        bad = bytearray(token(37, 7))
        bad[2] ^= 1 << bit
        prefix.append(bytes(bad))
    await transact(controller, phy, 22, b"\xa5", address=37, endpoint=7, prefix=prefix)


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_transaction_phase_frequency(dut):
    controller, phy = await setup(dut)
    ident = 100
    for phase in [1, 5000, 10000, 15000, 19999]:
        for ppm in [-1000, 0, 1000]:
            await transact(
                controller,
                phy,
                ident,
                b"\xff\x00\x55\xaa\x01\x80\x7f\xfe",
                address=37,
                endpoint=7,
                phase_ps=phase,
                ppm=ppm,
            )
            ident += 1
        await transact(
            controller,
            phy,
            ident,
            b"\x00\x01\x02\x03\x04\x05\x06\x07",
            token_pid=0x2D,
            phase_ps=phase,
            ppm=1000,
        )
        ident += 1
    Path("out_phase_timings.json").write_text(json.dumps(phy.timings, indent=2) + "\n")


@cocotb.test(timeout_time=25, timeout_unit="ms")
async def test_transaction_error_timeout_recovery(dut):
    controller, phy = await setup(dut)
    payload = b"\xa5"
    packet = b"\xc3" + payload + crc16(payload)
    bad = packet[:-1] + bytes([packet[-1] ^ 1])
    await transact(controller, phy, 200, payload, packets=[token(0, 0), bad], status=16)
    await transact(
        controller, phy, 201, b"\x00" * 8, token_pid=0x2D, pid=0x4B, status=21
    )
    await transact(controller, phy, 202, b"\x00" * 7, token_pid=0x2D, status=17)
    # Orphan data is ignored; then the bounded wait expires without ACK/output.
    await transact(controller, phy, 203, payload, packets=[packet], status=6)
    await transact(controller, phy, 204, payload)
    # Continuous ignored traffic cannot defeat the per-request SOP budget.
    await transact(controller, phy, 205, payload, packets=[token(1, 0)] * 16, status=6)
    await transact(controller, phy, 206, payload)


async def data_waveform(phy, payload, pid):
    for _ in range(50000):
        if phy.device_active:
            break
        await Timer(20, unit="ns")
    else:
        raise AssertionError("No IN data response")
    start = int(phy.ack_start)
    expected, stuffed = encode(bytes([pid]) + payload + crc16(payload))
    for index, state in enumerate(expected):
        at = start + round((index + 0.5) * 1e12 / 1.5e6)
        await Timer(at - int(get_sim_time(unit="ps")), unit="ps")
        enabled, actual, _ = phy.controls()
        assert enabled and actual == state, (
            index,
            enabled,
            actual,
            state,
            payload.hex(),
        )
    end_j = start + round((len(expected) - 1) * 1e12 / 1.5e6)
    await Timer(500, unit="ns")
    assert not phy.controls()[0], "IN driver not released after EOP"
    for when, _state in phy.device_transitions:
        nominal = round((when - start) / (1e12 / 1.5e6))
        assert abs(when - start - nominal * 1e12 / 1.5e6) <= 20000
    return start, end_j, len(stuffed)


async def in_transaction(
    controller,
    phy,
    ident,
    payload,
    *,
    pid=0xC3,
    address=0,
    endpoint=0,
    retries=0,
    ppm=0,
    phase_ps=1,
    no_ack=False,
    prefix=None,
    rejected_ack=None,
):
    request = Request(
        ident, 1, arguments_length=41, input_count=len(payload), output_limit=0
    )
    phy.ack_start = None
    await controller.submit(
        request, payload, bytes([1, *CONSTANTS, address, endpoint, pid, 1])
    )
    # All CRC and line encoding is firmware, performed before token reception.
    await Timer(10, unit="us")
    if prefix:
        await send_packets(phy, prefix, ppm=ppm, phase_ps=phase_ps)
        await Timer(3, unit="us")
        assert phy.ack_start is None
    for attempt in range(retries + 1):
        phy.ack_start = None
        watcher = cocotb.start_soon(data_waveform(phy, payload, pid))
        endings = await send_packets(
            phy, [token(address, endpoint, 0x69)], ppm=ppm, phase_ps=phase_ps
        )
        start, end_j, stuff = await watcher
        latency = start - endings[0]
        assert 2e12 / 1.5e6 <= latency <= 6.5e12 / 1.5e6, latency
        phy.timings.append(
            {
                "direction": "IN",
                "payload_bytes": len(payload),
                "pid": pid,
                "attempt": attempt,
                "phase_ps": phase_ps,
                "relative_ppm": ppm,
                "response_latency_ps": latency,
                "stuffed_bits": stuff,
            }
        )
        if attempt < retries:
            # Lost host ACK: repeated IN must resend identical PID/data/FCS.
            if rejected_ack is not None:
                at = end_j + round(2e12 / 1.5e6)
                await Timer(at - int(get_sim_time(unit="ps")), unit="ps")
                states, _ = encode(rejected_ack)
                await phy.send(states, ppm=ppm, phase_ps=phase_ps)
            await Timer(10, unit="us")
    if not no_ack:
        # Minimum host turnaround, measured from the device SE0->J edge.
        at = end_j + round(2e12 / 1.5e6)
        await Timer(at - int(get_sim_time(unit="ps")), unit="ps")
        states, _ = encode(b"\xd2")
        await phy.send(states, ppm=ppm, phase_ps=phase_ps)
    output, event = await controller.complete(request, poll_limit=100000)
    assert output == [] and event.status == (6 if no_ack else 0), event
    assert event.input_consumed == len(payload) and event.output_produced == 0
    if not no_ack:
        assert event.detail == 0x69, event
    assert not phy.controls()[0]
    assert await controller.read(0x101) == 0


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_in_arbitrary_payload_and_retry(dut):
    controller, phy = await setup(dut)
    rng = random.Random(0x494E)
    for length in range(9):
        await in_transaction(
            controller,
            phy,
            300 + length,
            bytes(rng.randrange(256) for _ in range(length)),
            address=37,
            endpoint=7,
            pid=0xC3 if length % 2 else 0x4B,
        )
    await in_transaction(controller, phy, 310, b"\xff" * 8, retries=2)
    await in_transaction(controller, phy, 311, bytes(8), pid=0x4B)
    # 0xf9 puts a mandatory stuffed zero after the last CRC bit.
    for pid in [0xC3, 0x4B]:
        await in_transaction(controller, phy, 316 + (pid == 0x4B), b"\xf9", pid=pid)
    await in_transaction(
        controller, phy, 318, b"\xa5", retries=1, rejected_ack=b"\xd2\x00"
    )
    # Both directions alternate on this same uploaded image, without reset.
    await transact(controller, phy, 312, b"\xa5\x5a", address=37, endpoint=7)
    await in_transaction(controller, phy, 313, b"\x42", address=37, endpoint=7)
    await transact(controller, phy, 314, bytes(8), token_pid=0x2D)
    await in_transaction(controller, phy, 315, b"\xff\x00", pid=0x4B)
    Path("in_timings.json").write_text(json.dumps(phy.timings, indent=2) + "\n")


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_in_filter_phase_frequency_and_recovery(dut):
    controller, phy = await setup(dut)
    ident = 400
    for phase in [1, 5000, 10000, 15000, 19999]:
        for ppm in [-1000, 0, 1000]:
            await in_transaction(
                controller,
                phy,
                ident,
                b"\xff\x00\x55\xaa\x01\x80\x7f\xfe",
                address=127,
                endpoint=15,
                ppm=ppm,
                phase_ps=phase,
            )
            ident += 1
    bad = bytearray(token(37, 7, 0x69))
    bad[2] ^= 8
    await in_transaction(
        controller,
        phy,
        ident,
        b"\x42",
        address=37,
        endpoint=7,
        prefix=[b"\xd2", token(36, 7, 0x69), token(37, 6, 0x69), bytes(bad)],
    )
    await in_transaction(controller, phy, ident + 1, b"\xa5", no_ack=True)
    await in_transaction(controller, phy, ident + 2, b"\x5a")
    Path("in_phase_timings.json").write_text(json.dumps(phy.timings, indent=2) + "\n")
