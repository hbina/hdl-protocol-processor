"""Independent post-error dominant-run counter oracle and wire/timing checks."""

import json
import os
import random
from itertools import pairwise
from pathlib import Path

import cocotb
from can_fault_equal_peer import counters, good_tx
from can_peer import frame
from can_recovery_peer import BIT, until
from can_rx_flags_peer import ReceivePeer, receive_good
from can_winner_peer import winner_request
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ValueChange, with_timeout
from cocotb.utils import get_sim_time
from frontier_peer import tx
from generic_call_frontier import assemble
from isa_variants import label_addresses

from test import PinController, load_program, reset
from tools.runtime import Request


def extra_count(pattern, receiver):
    # Independent normative oracle, not a translation of the firmware branches.
    bonus = 8 if receiver and pattern and pattern[0] == 0 else 0
    run = 0
    for bit in pattern[:32]:
        run = run + 1 if bit == 0 else 0
        if run and run % 8 == 0:
            bonus += 8
    return bonus


class PostflagPeer(ReceivePeer):
    async def delimiter_trace(self, source):
        labels = label_addresses(source)
        core = self.dut.user_project.core
        while True:
            await ValueChange(core.pc)
            await Timer(1, unit="ps")
            if int(core.pc.value) == labels["error_delimiter_sample"]:
                while int(core.wait_count.value):
                    await RisingEdge(self.dut.clk)
                    await Timer(1, unit="ps")
                await RisingEdge(self.dut.clk)
                self.delimiter_samples.append(int(get_sim_time(unit="ps")))

    async def drive_error(
        self,
        identifier,
        data,
        pattern,
        *,
        receiver,
        passive,
        fault="crc",
        prefix="recessive",
    ):
        wire, ack, stuffing = frame(
            identifier, data, crc_error=receiver and fault == "crc"
        )
        if receiver:
            if fault == "crc":
                failed_at, status, acknowledge = ack + 1, 16, False
            elif fault == "stuff":
                assert stuffing
                failed_at, status, acknowledge = stuffing[0], 19, False
                wire[failed_at] ^= 1
            else:
                failed_at, status, acknowledge = ack + 1, 17, True
                wire[failed_at] = 0
            start = int(get_sim_time(unit="ps"))
        else:
            failed_at = (
                ack
                if fault == "ack"
                else next(i for i in range(20, ack - 2) if wire[i] == 1)
            )
            status, acknowledge = (24 if fault == "ack" else 21), False
            start = await with_timeout(self.sof(), 2, "ms")
        edges_start = len(self.ack_edges)
        for index in range(failed_at + 1):
            self.sender = (
                wire[index]
                if receiver
                else int(not (fault != "ack" and index == failed_at))
            )
            await until(start + index * BIT + BIT * 3 // 4)
            expected = (
                int(not (acknowledge and index == ack)) if receiver else wire[index]
            )
            assert self.drive() == expected, (
                receiver,
                fault,
                index,
                self.drive(),
                expected,
            )
            await until(start + (index + 1) * BIT)
        flag_start = start + (failed_at + 1) * BIT
        flag_cells = 9 if passive and prefix == "mixed" else 6
        for index in range(flag_cells):
            self.sender = int(
                not (prefix == "dominant" or prefix == "mixed" and index in (1, 2))
            )
            await until(flag_start + index * BIT + BIT * 3 // 4)
            assert self.drive() == int(passive), (
                "flag",
                passive,
                prefix,
                index,
                self.drive(),
            )
            await until(flag_start + (index + 1) * BIT)
        post_start = flag_start + flag_cells * BIT
        for index, bit in enumerate(list(pattern) + [1] * 11):
            self.sender = bit
            await until(post_start + index * BIT + BIT * 3 // 4)
            assert self.drive() == 1, ("post-flag drive", index, self.drive())
            await until(post_start + (index + 1) * BIT)
        self.sender = 1
        await Timer(20, unit="ns")
        edges = self.ack_edges[edges_start:]
        record = {
            "receiver": receiver,
            "fault": fault,
            "passive": passive,
            "prefix": prefix,
            "pattern": list(pattern),
            "flag_start_ps": flag_start,
            "flag_cells": flag_cells,
            "post_start_ps": post_start,
            "intermission_end_ps": post_start + (len(pattern) + 11) * BIT,
            "status": status,
            "extra_count": extra_count(pattern, receiver),
            "pin_edges_ns": edges,
        }
        if not passive:
            assert edges[-2][1] == 0 and edges[-1][1] == 1
            assert edges[-1][0] - edges[-2][0] == 48000, edges
        return record


async def setup(dut):
    assert os.environ.get("CAN_POSTFLAG_EXPERIMENT") == "1"
    source = Path(os.environ["CAN_POSTFLAG_SOURCE"]).read_text()
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    bus = PostflagPeer(dut)
    bus.delimiter_samples = []
    cocotb.start_soon(bus.resolve())
    await load_program(dut, assemble(source))
    cocotb.start_soon(bus.trace_samples(source))
    cocotb.start_soon(bus.delimiter_trace(source))
    return PinController(dut, 0x504F5354), bus


async def exchange_error(
    controller,
    bus,
    ident,
    tec,
    rec,
    pattern,
    *,
    receiver=True,
    fault="crc",
    prefix="recessive",
):
    passive = tec >= 128 or rec >= 128
    request = Request(
        ident,
        1 if receiver else 2,
        arguments_length=0 if receiver else 3,
        input_count=0 if receiver else 1,
        output_limit=11 if receiver else 0,
    )
    listener = None
    sample_start = len(bus.delimiter_samples)
    if not receiver:
        listener = cocotb.start_soon(
            bus.drive_error(
                0x321,
                b"\xa5",
                pattern,
                receiver=False,
                passive=passive,
                fault=fault,
                prefix=prefix,
            )
        )
    await controller.submit(
        request, b"" if receiver else b"\xa5", b"" if receiver else b"\x03\x21\x01"
    )
    if receiver:
        await Timer(110, unit="us")
        listener = cocotb.start_soon(
            bus.drive_error(
                0x123,
                b"\xa5",
                pattern,
                receiver=True,
                passive=passive,
                fault=fault,
                prefix=prefix,
            )
        )
    output, event = await controller.complete(request, poll_limit=100000)
    completed = int(get_sim_time(unit="ps"))
    record = await listener
    base = (
        1
        if receiver
        else (8 if fault != "ack" or not passive or prefix != "recessive" else 0)
    )
    if receiver:
        rec = min(255, rec + base + record["extra_count"])
    else:
        tec += base + record["extra_count"]
    timeout = len(pattern) + 8 > 32
    expected_status = 25 if timeout else 26 if tec >= 256 else record["status"]
    assert output == [] and event.status == expected_status, (event, record)
    assert event.input_consumed == request.input_count and event.output_produced == 0
    assert event.detail == int(not receiver)
    assert await counters(controller, ident + 10000) == (tec, rec), (tec, rec, record)
    assert await controller.read(0x101) == 0
    if not timeout:
        assert completed >= record["intermission_end_ps"] - 1000, (completed, record)
    samples = bus.delimiter_samples[sample_start:]
    assert all(b - a == BIT for a, b in pairwise(samples)), (record, samples)
    assert len(samples) == (32 if timeout else len(pattern) + 8), (record, samples)
    record.update(
        {
            "tec_after": tec,
            "rec_after": rec,
            "terminal_status": event.status,
            "delimiter_samples_ps": samples,
        }
    )
    return tec, rec, record


@cocotb.test(timeout_time=40, timeout_unit="ms")
async def test_receiver_postflag_dominance(dut):
    controller, bus = await setup(dut)
    tec = rec = 0
    rows = []
    patterns = [
        [0],
        [],
        [0] * 7,
        [1, 0],
        [1] + [0] * 8,
        [0] * 8,
        [0] * 16,
        [0] * 24,
        [0] * 32,
        [0] * 7 + [1, 0],
        [0] * 8 + [1] + [0] * 8,
    ]
    for index, pattern in enumerate(patterns):
        tec, rec, row = await exchange_error(
            controller,
            bus,
            index,
            tec,
            rec,
            pattern,
            fault=["crc", "stuff", "form"][index % 3],
        )
        rows.append(row)
    await receive_good(controller, bus, 50, 0x456, b"\x5a")
    assert await counters(controller, 10050) == (tec, rec - 1 if rec <= 127 else 127)
    Path("receiver_postflag_timings.json").write_text(json.dumps(rows, indent=2) + "\n")


@cocotb.test(timeout_time=45, timeout_unit="ms")
async def test_postflag_threshold_and_saturation(dut):
    controller, bus = await setup(dut)
    tec = rec = 0
    for index in range(14):
        tec, rec, _ = await exchange_error(controller, bus, 100 + index, tec, rec, [0])
    assert rec == 126
    tec, rec, _ = await exchange_error(controller, bus, 114, tec, rec, [])
    assert rec == 127
    tec, rec, row = await exchange_error(controller, bus, 115, tec, rec, [0])
    assert rec == 136 and not row["passive"]
    tec, rec, row = await exchange_error(
        controller, bus, 116, tec, rec, [0] * 8, prefix="mixed"
    )
    assert rec == 153 and row["passive"] and row["flag_cells"] == 9
    for index in range(5):
        tec, rec, _ = await exchange_error(
            controller, bus, 120 + index, tec, rec, [0] * 16
        )
    assert rec == 255 and int(dut.uio_oe.value) == 1
    tec, rec, _ = await exchange_error(controller, bus, 125, tec, rec, [0])
    assert rec == 255
    await receive_good(controller, bus, 126, 0x456, b"\x5a")
    assert await counters(controller, 10126) == (0, 127)


@cocotb.test(timeout_time=45, timeout_unit="ms")
async def test_transmitter_postflag_counts(dut):
    controller, bus = await setup(dut)
    tec = rec = 0
    rows = []
    for index, pattern in enumerate(
        [[0], [0] * 7, [0] * 8, [1] + [0] * 8, [0] * 16, [0] * 24, [0] * 32]
    ):
        tec, rec, row = await exchange_error(
            controller, bus, 200 + index, tec, rec, pattern, receiver=False, fault="bit"
        )
        rows.append(row)
    assert (tec, rec) == (144, 0)
    tec, rec, _ = await exchange_error(
        controller, bus, 210, tec, rec, [0], receiver=False, fault="ack"
    )
    assert tec == 144
    tec, rec, _ = await exchange_error(
        controller, bus, 211, tec, rec, [0] * 8, receiver=False, fault="ack"
    )
    assert tec == 152
    tec, rec, _ = await exchange_error(
        controller,
        bus,
        212,
        tec,
        rec,
        [0] * 8,
        receiver=False,
        fault="ack",
        prefix="dominant",
    )
    assert tec == 168
    await good_tx(controller, bus, 213, expected_tec=167)
    Path("transmitter_postflag_timings.json").write_text(
        json.dumps(rows, indent=2) + "\n"
    )


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_postflag_bus_off_recovery(dut):
    controller, bus = await setup(dut)
    tec = rec = 0
    for index in range(16):
        tec, rec, _ = await exchange_error(
            controller, bus, 300 + index, tec, rec, [0] * 8, receiver=False, fault="bit"
        )
    assert (tec, rec) == (256, 0) and int(dut.uio_oe.value) == 0
    request = Request(350, 2, arguments_length=3, input_count=8)
    await controller.submit(request, b"\xaa" * 8, b"\x01\x23\x08")
    output, event = await controller.complete(request, poll_limit=30000)
    assert output == [] and event.status == 26 and event.input_consumed == 8
    bus.sender = 0
    recovery = Request(351, 5)
    await controller.submit(recovery, b"")
    await Timer(3 * BIT, unit="ps")
    bus.sender = 1
    await Timer(49 * BIT, unit="ps")
    bus.sender = 0
    await Timer(BIT, unit="ps")
    bus.sender = 1
    started = int(get_sim_time(unit="ps"))
    await Timer(10.9, unit="ms")
    assert int(dut.uio_oe.value) == 0
    await with_timeout(ValueChange(dut.uio_oe), 40, "us")
    assert (
        124 * 11 * BIT
        <= int(get_sim_time(unit="ps")) - started
        <= 124 * 11 * BIT + 2 * BIT
    )
    output, event = await controller.complete(recovery, poll_limit=50000)
    assert (
        output == []
        and event.status == 0
        and await counters(controller, 10351) == (0, 0)
    )
    await good_tx(controller, bus, 352, expected_tec=0)


@cocotb.test(timeout_time=45, timeout_unit="ms")
async def test_postflag_profile_and_protocol_regression(dut):
    controller, bus = await setup(dut)
    # Unsupported header/tail profile exits must not charge a second local REC.
    for index, kind in enumerate(["rtr", "dlc", "last_eof", "intermission"]):
        request = Request(400 + index, 1, output_limit=11)
        await controller.submit(request, b"")
        await Timer(110, unit="us")
        wire, ack, _ = frame(
            0x123,
            b"",
            header_flags=(1, 0, 0) if kind == "rtr" else (0, 0, 0),
            dlc=9 if kind == "dlc" else None,
        )
        if kind in {"last_eof", "intermission"}:
            wire[ack + (8 if kind == "last_eof" else 9)] = 0

        async def local_wave(wire=wire, ack=ack, kind=kind):
            for bit_index, bit in enumerate(wire):
                bus.sender = bit
                await Timer(6, unit="us")
                assert bus.drive() == int(
                    not (kind in {"last_eof", "intermission"} and bit_index == ack)
                )
                await Timer(2, unit="us")
            bus.sender = 1

        listener = cocotb.start_soon(local_wave())
        output, event = await controller.complete(request, poll_limit=50000)
        await listener
        assert output == [] and event.status == (18 if kind in {"rtr", "dlc"} else 17)
        assert await counters(controller, 10400 + index) == (0, 0)
    rng = random.Random(0x524F54415445)
    for length in [0, 1, 8]:
        data = bytes(rng.randrange(256) for _ in range(length))
        await tx(controller, bus, 420 + length, rng.randrange(2048), data)
        await receive_good(
            controller, bus, 440 + length, rng.randrange(2048), data[::-1]
        )
    for index, ppm in enumerate([-5000, 0, 5000]):
        await receive_good(
            controller,
            bus,
            460 + index,
            0x6A5,
            b"\x00\xff\x55\xaa\x01\x80\x00\xff",
            ppm=ppm,
            jumps=True,
            phase_ns=19,
        )
    await winner_request(
        controller,
        bus,
        470,
        0x7FF,
        b"\xaa" * 8,
        [(0x123, bytes(8)), (0x456, b"\x55" * 8)],
    )
    assert await counters(controller, 10470) == (0, 0)
    bus.oracle_tec = 0
    await winner_request(
        controller,
        bus,
        471,
        0x7FF,
        b"\x55\xaa\xff\x00",
        [(0x123, b"\x12\x34")],
        ack_failures=1,
    )
    assert await counters(controller, 10471) == (7, 0)
