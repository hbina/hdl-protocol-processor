"""Independent CAN receive-error wire timing, counters and compact-code peers."""

import json
import os
import random
from pathlib import Path

import cocotb
from can_fault_equal_peer import FaultPeer, counters, fail_once, good_tx
from can_peer import frame
from can_recovery_peer import BIT, until
from can_resync_peer import DriftPeer
from can_winner_peer import winner_request
from cocotb.clock import Clock
from cocotb.triggers import Timer, ValueChange, with_timeout
from cocotb.utils import get_sim_time
from frontier_peer import tx
from generic_call_frontier import assemble

from test import PinController, load_program, reset
from tools.runtime import Request


class ReceivePeer(FaultPeer):
    drifting_frame = DriftPeer.drifting_frame
    trace_samples = DriftPeer.trace_samples

    async def error_frame(
        self, identifier, data, *, fault, passive=False, overlap=False
    ):
        wire, ack, stuffing = frame(identifier, data, crc_error=fault == "crc")
        acknowledge = False
        if fault == "crc":
            failed_at = ack + 1  # Deferred until after ACK delimiter.
            status = 16
        elif fault in {"stuff", "crc_and_stuff"}:
            if fault == "crc_and_stuff":
                wire, ack, stuffing = frame(identifier, data, crc_error=True)
                assert stuffing and stuffing[-1] == ack - 2
                failed_at = stuffing[-1]
            else:
                assert stuffing
                failed_at = stuffing[0]
            wire[failed_at] ^= 1
            status = 19
        else:
            failed_at = {
                "crc_delimiter": ack - 1,
                "ack_delimiter": ack + 1,
                "eof_first": ack + 2,
                "eof_sixth": ack + 7,
            }[fault]
            wire[failed_at] = 0
            acknowledge = failed_at > ack
            status = 17
        start = int(get_sim_time(unit="ps"))
        first_edge = len(self.ack_edges)
        for index in range(failed_at + 1):
            self.sender = wire[index]
            await until(start + index * BIT + BIT * 3 // 4)
            assert self.drive() == int(not (acknowledge and index == ack)), (
                fault,
                index,
                ack,
                self.drive(),
            )
            await until(start + (index + 1) * BIT)
        flag_start = start + (failed_at + 1) * BIT
        self.sender = 1
        await Timer(
            500, unit="ns"
        )  # Less than one bit; allow synchronized-input phase.
        assert self.drive() == int(passive), (
            fault,
            "flag start",
            passive,
            self.drive(),
        )
        flag_cells = 9 if passive and overlap else 6
        for index in range(flag_cells):
            self.sender = 0 if overlap and index in (1, 2) else 1
            await until(flag_start + index * BIT + BIT * 3 // 4)
            assert self.drive() == int(passive), (fault, index, passive, self.drive())
            await until(flag_start + (index + 1) * BIT)
        self.sender = 1
        for index in range(11):
            await until(flag_start + (flag_cells + index) * BIT + BIT * 3 // 4)
            assert self.drive() == 1
            await until(flag_start + (flag_cells + index + 1) * BIT)
        await Timer(20, unit="ns")
        edges = self.ack_edges[first_edge:]
        record = {
            "fault": fault,
            "status": status,
            "identifier": identifier,
            "dlc": len(data),
            "physical_start_ps": start,
            "fault_wire_bit": failed_at,
            "expected_flag_start_ps": flag_start,
            "passive": passive,
            "flag_cells": flag_cells,
            "intermission_end_ps": flag_start + (flag_cells + 11) * BIT,
            "pin_edges_ns": edges,
            "crc_ack_wire_bit": ack,
            "final_crc_stuff": bool(stuffing and stuffing[-1] == ack - 2),
        }
        if not passive:
            fall, rise = edges[-2:]
            assert fall[1] == 0 and rise[1] == 1
            phase = round(fall[0] * 1000) - flag_start
            assert 0 <= phase <= 300_000, (fault, phase, edges)
            assert rise[0] - fall[0] == 48000, (fault, edges)
            record["flag_edge_delay_ps"] = phase
            record["flag_duration_clocks"] = round((rise[0] - fall[0]) / 20)
        return record


async def setup(dut):
    assert os.environ.get("CAN_RX_FLAGS_EXPERIMENT") == "1"
    source = Path(os.environ["CAN_RX_FLAGS_SOURCE"]).read_text()
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    bus = ReceivePeer(dut)
    cocotb.start_soon(bus.resolve())
    await load_program(dut, assemble(source))
    cocotb.start_soon(bus.trace_samples(source))
    return PinController(dut, 0x5258464C4147), bus


async def receive_error(
    controller,
    bus,
    ident,
    identifier,
    data,
    *,
    fault="crc",
    passive=False,
    overlap=False,
):
    request = Request(ident, 1, output_limit=11)
    await controller.submit(request, b"")
    await Timer(110, unit="us")
    listener = cocotb.start_soon(
        bus.error_frame(identifier, data, fault=fault, passive=passive, overlap=overlap)
    )
    output, event = await controller.complete(request, poll_limit=100000)
    completed = int(get_sim_time(unit="ps"))
    record = await listener
    assert output == [] and event.status == record["status"], (output, event, record)
    assert (
        event.input_consumed == 0 and event.output_produced == 0 and event.detail == 0
    )
    assert completed >= record["intermission_end_ps"] - 1000, (completed, record)
    assert await controller.read(0x101) == 0
    return record


async def receive_good(
    controller, bus, ident, identifier, data, *, ppm=0, phase_ns=1, jumps=False
):
    request = Request(ident, 1, output_limit=11)
    await controller.submit(request, b"")
    await Timer(110, unit="us")
    sample_start = len(bus.samples)
    listener = cocotb.start_soon(
        bus.drifting_frame(identifier, data, ppm=ppm, phase_ns=phase_ns, jumps=jumps)
    )
    output, event = await controller.complete(request, poll_limit=50000)
    record = await listener
    assert output == [
        (byte, 0)
        for byte in bytes([identifier >> 8, identifier & 255, len(data)]) + data
    ]
    assert (
        event.status == 0
        and event.output_produced == len(data) + 3
        and event.input_consumed == 0
    )
    assert await controller.read(0x101) == 0
    samples = bus.samples[sample_start:]
    assert len(samples) == record["ack_wire_bit"]
    phases = [
        (sample - begin) / (end - begin)
        for sample, begin, end in zip(
            samples, record["boundaries_ps"], record["boundaries_ps"][1:]
        )
    ]
    assert all(0 < phase < 1 for phase in phases), phases
    record.update({"sample_phase_min": min(phases), "sample_phase_max": max(phases)})
    return record


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_receiver_error_flags(dut):
    controller, bus = await setup(dut)
    records = []
    rec = 0
    for index, fault in enumerate(
        ["crc", "stuff", "crc_delimiter", "ack_delimiter", "eof_first", "eof_sixth"]
    ):
        records.append(
            await receive_error(controller, bus, index, 0, bytes(8), fault=fault)
        )
        rec += 1
        assert await counters(controller, 1000 + index) == (0, rec)
    for identifier in range(2048):
        _, ack, stuffing = frame(identifier, b"\xa5", crc_error=True)
        if stuffing and stuffing[-1] == ack - 2:
            records.append(
                await receive_error(
                    controller, bus, 10, identifier, b"\xa5", fault="crc"
                )
            )
            records.append(
                await receive_error(
                    controller, bus, 11, identifier, b"\xa5", fault="crc_and_stuff"
                )
            )
            rec += 2
            break
    else:
        raise AssertionError("No corrupted-CRC final-stuff vector")
    assert await counters(controller, 1011) == (0, rec)
    await receive_good(controller, bus, 12, 0x456, b"\x5a")
    assert await counters(controller, 1012) == (0, rec - 1)
    Path("rx_error_timings.json").write_text(json.dumps(records, indent=2) + "\n")


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_compact_pack_unpack_and_phase(dut):
    controller, bus = await setup(dut)
    rng = random.Random(0x5041434B)
    records = []
    for length in range(9):
        data = bytes(rng.randrange(256) for _ in range(length))
        await tx(controller, bus, length * 2, rng.randrange(2048), data)
        records.append(
            await receive_good(
                controller, bus, length * 2 + 1, rng.randrange(2048), data[::-1]
            )
        )
    for index, ppm in enumerate([-5000, 0, 5000]):
        records.append(
            await receive_good(
                controller,
                bus,
                40 + index,
                0x6A5,
                b"\x00\xff\x55\xaa\x01\x80\x00\xff",
                ppm=ppm,
                jumps=True,
                phase_ns=19,
            )
        )
    Path("compact_phase_timings.json").write_text(json.dumps(records, indent=2) + "\n")


@cocotb.test(timeout_time=220, timeout_unit="ms")
async def test_receiver_passive_counter_and_saturation(dut):
    controller, bus = await setup(dut)
    for index in range(256):
        await receive_error(
            controller,
            bus,
            100 + index,
            0x123,
            b"",
            passive=index >= 128,
            overlap=index == 128,
        )
        if (index + 1) % 16 == 0:
            assert await counters(controller, 2000 + index) == (0, min(255, index + 1))
    assert int(dut.uio_oe.value) == 1
    await receive_good(controller, bus, 400, 0x123, b"\x5a")
    assert await counters(controller, 2400) == (0, 127)
    await receive_error(controller, bus, 401, 0x123, b"")
    assert await counters(controller, 2401) == (0, 128)


@cocotb.test(timeout_time=40, timeout_unit="ms")
async def test_receiver_flags_tx_state_and_winners(dut):
    controller, bus = await setup(dut)
    await receive_error(controller, bus, 500, 0x123, b"\xa5")
    assert await counters(controller, 2500) == (0, 1)
    await receive_good(controller, bus, 501, 0x123, b"\x5a")
    tec = 0
    for index in range(16):
        tec, _ = await fail_once(controller, bus, 510 + index, tec=tec)
    tec, _ = await fail_once(controller, bus, 530, tec=tec)
    assert tec == 128
    await good_tx(controller, bus, 531, expected_tec=127)
    await winner_request(
        controller,
        bus,
        532,
        0x7FF,
        b"\xaa" * 8,
        [(0x123, bytes(8)), (0x456, b"\x55" * 8)],
    )
    assert await counters(controller, 2532) == (126, 0)
    bus.oracle_tec = 126
    await winner_request(
        controller,
        bus,
        533,
        0x7FF,
        b"\x55\xaa\xff\x00",
        [(0x123, b"\x12\x34")],
        ack_failures=1,
    )
    assert await counters(controller, 2533) == (133, 0)


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_compact_bus_off_recovery(dut):
    controller, bus = await setup(dut)
    tec = 0
    for index in range(32):
        tec, _ = await fail_once(controller, bus, 600 + index, tec=tec, bit_error=True)
    assert tec == 256 and int(dut.uio_oe.value) == 0
    request = Request(650, 2, arguments_length=3, input_count=8)
    await controller.submit(request, b"\xaa" * 8, b"\x01\x23\x08")
    output, event = await controller.complete(request, poll_limit=30000)
    assert output == [] and event.status == 26 and event.input_consumed == 8
    bus.sender = 0
    recovery = Request(651, 5)
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
    elapsed = int(get_sim_time(unit="ps")) - started
    assert 124 * 11 * BIT <= elapsed <= 124 * 11 * BIT + 2 * BIT
    output, event = await controller.complete(recovery, poll_limit=50000)
    assert output == [] and event.status == 0
    assert await counters(controller, 2651) == (0, 0)
    await receive_good(controller, bus, 652, 0x123, b"\x5a")
