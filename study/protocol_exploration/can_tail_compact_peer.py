"""CAN tail peer plus a busy-bus regression for bit-preserving input reads."""

import can_tail_peer as base
import cocotb
from can_fault_equal_peer import counters
from frontier_peer import tx

from tools.runtime import Request


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_last_eof_dominant_acceptance(dut):
    await base.test_last_eof_dominant_acceptance.func(dut)


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_intermission_overload(dut):
    await base.test_intermission_overload.func(dut)


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_third_intermission_sof_classification(dut):
    await base.test_third_intermission_sof_classification.func(dut)


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_normal_frame_tail_control(dut):
    await base.test_normal_frame_tail_control.func(dut)


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_busy_transmit_qualification(dut):
    controller, bus = await base.setup(dut)
    before = len(bus.ack_edges)
    bus.sender = 0
    request = Request(100, 2, arguments_length=3, input_count=1)
    await controller.submit(request, b"\xa5", b"\x03\x21\x01")
    output, event = await controller.complete(request, poll_limit=100000)
    assert output == [] and event.status == 6, event
    assert (
        event.input_consumed == 1 and event.output_produced == 0 and event.detail == 1
    )
    assert bus.ack_edges[before:] == [], bus.ack_edges[before:]
    assert await counters(controller, 10100) == (0, 0)
    bus.sender = 1
    await tx(controller, bus, 101, 0x321, b"\x5a")
    assert await counters(controller, 10101) == (0, 0)


async def overload_sequence(bus, *, last_delimiter=False, exhaust=False):
    from can_peer import frame
    from can_recovery_peer import BIT, until
    from cocotb.utils import get_sim_time

    wire, ack, _ = frame(0x321, b"\xa5")
    wire = wire[: ack + 10]  # Through first intermission.
    wire[-1] = 0
    actions = [(bit, int(index != ack)) for index, bit in enumerate(wire)]
    starts = []
    for index in range(2):
        starts.append(len(actions))
        actions += [(1, 0)] * 6
        delimiter = [1] * 8
        if last_delimiter and index == 0:
            delimiter[-1] = 0
        actions += [(bit, 1) for bit in delimiter]
        if index == 0 and not last_delimiter:
            actions += [(0, 1)]  # Another overload trigger at first intermission.
    actions += [(0 if exhaust else 1, 1), (1, 1), (1, 1)]
    # Enough recessive tail to prove no third flag and allow bounded completion.
    if exhaust:
        actions += [(1, 1)] * 20
    started = int(get_sim_time(unit="ps"))
    for index, (sent, expected) in enumerate(actions):
        bus.sender = sent
        await until(started + index * BIT + BIT * 3 // 4)
        assert bus.drive() == expected, (index, starts, sent, expected, bus.drive())
        await until(started + (index + 1) * BIT)
    bus.sender = 1
    return {
        "last_delimiter": last_delimiter,
        "exhaust": exhaust,
        "overload_start_cells": starts,
        "frame_start_ps": started,
        "commanded_edges_ns": bus.ack_edges.copy(),
    }


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_repeated_overload_delimiter_and_bound(dut):
    import json
    from pathlib import Path

    from cocotb.triggers import Timer

    controller, bus = await base.setup(dut)
    rows = []
    for index, (last, exhaust) in enumerate(
        [(False, False), (True, False), (False, True)]
    ):
        request = Request(200 + index, 1, output_limit=11)
        await controller.submit(request, b"")
        await Timer(110, unit="us")
        task = cocotb.start_soon(
            overload_sequence(bus, last_delimiter=last, exhaust=exhaust)
        )
        output, event = await controller.complete(request, poll_limit=100000)
        rows.append(await task)
        expected = [] if exhaust else [(3, 0), (0x21, 0), (1, 0), (0xA5, 0)]
        assert output == expected and event.status == (25 if exhaust else 0), event
        assert (
            event.input_consumed == 0
            and event.output_produced == len(expected)
            and event.detail == 0
        )
        assert await counters(controller, 10200 + index) == (0, 0)
    await base.receive(controller, bus, 210, 0x123, b"\x5a", "normal")
    Path("repeated_overload_timings.json").write_text(json.dumps(rows, indent=2) + "\n")


@cocotb.test(timeout_time=45, timeout_unit="ms")
async def test_passive_node_still_sends_dominant_overload(dut):
    from can_fault_equal_peer import fail_once
    from cocotb.triggers import Timer

    controller, bus = await base.setup(dut)
    tec = 0
    for index in range(16):
        tec, _ = await fail_once(controller, bus, 300 + index, tec=tec)
    assert tec == 128
    request = Request(320, 1, output_limit=11)
    await controller.submit(request, b"")
    await Timer(110, unit="us")
    task = cocotb.start_soon(bus.tail_frame(0x321, b"\xa5", "first_intermission"))
    output, event = await controller.complete(request, poll_limit=100000)
    await task
    assert output == [(3, 0), (0x21, 0), (1, 0), (0xA5, 0)] and event.status == 0
    assert await counters(controller, 10320) == (128, 0)
