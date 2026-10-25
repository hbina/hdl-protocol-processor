"""Full position sweeps, repeated active-flag faults and state transitions."""

import json
import os
from itertools import pairwise
from pathlib import Path

import can_flag_bit_peer as original
import can_postflag_peer as postflag
import cocotb
from can_fault_equal_peer import counters, good_tx
from can_peer import frame
from can_recovery_peer import BIT, until
from can_rx_flags_peer import receive_good
from cocotb.triggers import RisingEdge, Timer, ValueChange, with_timeout
from cocotb.utils import get_sim_time
from isa_variants import label_addresses

from tools.runtime import Request


async def trace_flags(bus):
    source = Path(os.environ["CAN_FLAG_BIT_SOURCE"]).read_text()
    labels = label_addresses(source)
    core = bus.dut.user_project.core
    while True:
        await ValueChange(core.pc)
        await Timer(1, unit="ps")
        if int(core.pc.value) == labels["flag_sample"]:
            while int(core.wait_count.value):
                await RisingEdge(bus.dut.clk)
                await Timer(1, unit="ps")
            await RisingEdge(bus.dut.clk)
            bus.flag_samples.append(int(get_sim_time(unit="ps")))


async def setup(dut):
    controller, bus = await original.setup(dut)
    bus.flag_samples = []
    cocotb.start_soon(trace_flags(bus))
    return controller, bus


async def schedule_faults(bus, cells, *, receiver, tec, rec):
    wire, ack, _ = frame(0x123 if receiver else 0x321, b"\xa5", crc_error=receiver)
    failed_at = (
        ack + 1 if receiver else next(i for i in range(20, ack - 2) if wire[i] == 1)
    )
    start = (
        int(get_sim_time(unit="ps"))
        if receiver
        else await with_timeout(bus.sof(), 2, "ms")
    )
    for index in range(failed_at + 1):
        bus.sender = wire[index] if receiver else int(index != failed_at)
        await until(start + index * BIT + BIT * 3 // 4)
        assert bus.drive() == (1 if receiver else wire[index])
        await until(start + (index + 1) * BIT)
    passive = tec >= 128 or rec >= 128
    assert not passive
    rec += int(receiver)
    tec += 8 * int(not receiver)
    flag_start = start + (failed_at + 1) * BIT
    bus.sender = 1
    remaining, index, consumed = 6, 0, []
    commands = []
    while remaining:
        assert index < 64
        fault = index in cells and not passive
        bus.observed_override = 1 if fault else None
        await until(flag_start + index * BIT + BIT * 3 // 4)
        assert bus.drive() == int(passive), (index, passive, tec, rec, bus.drive())
        commands.append(int(passive))
        await until(flag_start + (index + 1) * BIT)
        if fault:
            consumed.append(index)
            passive = tec >= 128 or rec >= 128  # State before this error's increment.
            tec += 8 * int(not receiver)
            rec = min(255, rec + 8 * int(receiver))
            remaining = 6  # The next bit starts a new six-bit flag.
        else:
            remaining -= 1
        index += 1
    assert consumed == cells, (cells, consumed)
    bus.observed_override = None
    for tail in range(11):
        await until(flag_start + (index + tail) * BIT + BIT * 3 // 4)
        assert bus.drive() == 1, ("tail", tail, bus.drive())
        await until(flag_start + (index + tail + 1) * BIT)
    return {
        "fault_cells": cells,
        "flag_cells": index,
        "commands": commands,
        "tec_after": tec,
        "rec_after": rec,
        "flag_start_ps": flag_start,
        "intermission_end_ps": flag_start + (index + 11) * BIT,
    }


async def exchange(controller, bus, ident, cells, *, receiver, tec, rec):
    request = Request(
        ident,
        1 if receiver else 2,
        arguments_length=0 if receiver else 3,
        input_count=0 if receiver else 1,
        output_limit=11 if receiver else 0,
    )
    begin = len(bus.flag_samples)
    task = None
    if not receiver:
        task = cocotb.start_soon(
            schedule_faults(bus, cells, receiver=False, tec=tec, rec=rec)
        )
    await controller.submit(
        request, b"" if receiver else b"\xa5", b"" if receiver else b"\x03\x21\x01"
    )
    if receiver:
        await Timer(110, unit="us")
        task = cocotb.start_soon(
            schedule_faults(bus, cells, receiver=True, tec=tec, rec=rec)
        )
    output, event = await controller.complete(request, poll_limit=100000)
    finished = int(get_sim_time(unit="ps"))
    row = await task
    assert output == [] and event.status == (16 if receiver else 21), (event, row)
    assert event.input_consumed == request.input_count and event.output_produced == 0
    assert (
        event.detail == int(not receiver)
        and finished >= row["intermission_end_ps"] - 1000
    )
    assert await counters(controller, ident + 10000) == (
        row["tec_after"],
        row["rec_after"],
    )
    samples = bus.flag_samples[begin:]
    assert len(samples) == row["flag_cells"], (samples, row)
    assert all(b - a == BIT for a, b in pairwise(samples)), (samples, row)
    assert all(
        0 < sample - (row["flag_start_ps"] + index * BIT) < BIT
        for index, sample in enumerate(samples)
    )
    row["flag_samples_ps"] = samples
    return row


@cocotb.test(timeout_time=35, timeout_unit="ms")
async def test_all_receiver_flag_positions(dut):
    await original.test_receiver_active_flag_bit_errors.func(dut)


@cocotb.test(timeout_time=35, timeout_unit="ms")
async def test_all_transmitter_flag_positions(dut):
    await original.test_transmitter_active_flag_bit_errors.func(dut)


@cocotb.test(timeout_time=45, timeout_unit="ms")
async def test_passive_dominance_control(dut):
    await original.test_passive_flag_dominance_is_not_bit_error.func(dut)


@cocotb.test(timeout_time=45, timeout_unit="ms")
async def test_repeated_receiver_faults_and_passive_restart(dut):
    controller, bus = await setup(dut)
    row = await exchange(
        controller, bus, 200, list(range(0, 34, 2)), receiver=True, tec=0, rec=0
    )
    assert row["rec_after"] == 137 and row["commands"][-6:] == [1] * 6
    assert row["commands"][:-6] == [0] * 33
    await receive_good(controller, bus, 201, 0x456, b"\x5a")
    assert await counters(controller, 10201) == (0, 127)
    # Original RX error at127 crosses128, so its flag is active. A new flag
    # bit error then starts a passive flag, without charging a second +1.
    next_row = await exchange(controller, bus, 202, [5], receiver=True, tec=0, rec=127)
    assert next_row["rec_after"] == 136 and next_row["commands"] == [0] * 6 + [1] * 6
    Path("receiver_flag_restart_timings.json").write_text(
        json.dumps([row, next_row], indent=2) + "\n"
    )


@cocotb.test(timeout_time=45, timeout_unit="ms")
async def test_transmitter_threshold_and_restart_timing(dut):
    controller, bus = await setup(dut)
    tec = rec = 0
    for index in range(7):
        tec, rec, _ = await postflag.exchange_error(
            controller, bus, 300 + index, tec, rec, [0] * 8, receiver=False, fault="bit"
        )
    tec, rec, _ = await postflag.exchange_error(
        controller, bus, 307, tec, rec, [], receiver=False, fault="bit"
    )
    assert tec == 120
    row = await exchange(controller, bus, 308, [0], receiver=False, tec=tec, rec=0)
    assert row["tec_after"] == 136 and row["commands"] == [0] + [1] * 6
    await good_tx(controller, bus, 309, expected_tec=135)
    Path("transmitter_flag_restart_timings.json").write_text(
        json.dumps([row], indent=2) + "\n"
    )
