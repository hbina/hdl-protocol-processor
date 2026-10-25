"""Independent CAN error-state checks driven by runtime queries and wire faults."""

import json
import os
from pathlib import Path

import cocotb
from can_peer import frame
from can_recovery_peer import BIT, until
from can_tx_peer import Receiver
from can_winner_peer import ArbitrationPeer, winner_request
from cocotb.clock import Clock
from cocotb.triggers import Timer, ValueChange, with_timeout
from cocotb.utils import get_sim_time
from frontier_peer import rx
from generic_call_frontier import assemble

from test import PinController, load_program, reset
from tools.runtime import Request


class FaultPeer(ArbitrationPeer):
    oracle_tec = 0

    async def retries(self, identifier, payload, acknowledgments, **_kwargs):
        records = []
        for acknowledge in acknowledgments:
            if acknowledge:
                start, bit_ns, count = await Receiver.listen(self, identifier, payload)
                self.oracle_tec = max(0, self.oracle_tec - 1)
                records.append(
                    {"completion_earliest_ps": round((start + bit_ns * count) * 1000)}
                )
            else:
                records.append(
                    await self.failed_transmission(
                        identifier, payload, passive=self.oracle_tec >= 128
                    )
                )
                if self.oracle_tec < 128:
                    self.oracle_tec += 8
        return records

    async def failed_transmission(
        self,
        identifier,
        payload,
        *,
        passive=False,
        bit_error=False,
        passive_dominant=False,
    ):
        wire, ack, _ = frame(identifier, payload)
        collision = (
            next(i for i in range(20, ack - 2) if wire[i] == 1) if bit_error else ack
        )
        start = await with_timeout(self.sof(), 2, "ms")
        for index in range(collision + 1):
            self.sender = 0 if bit_error and index == collision else 1
            await until(start + index * BIT + BIT * 3 // 4)
            assert self.drive() == wire[index], (
                index,
                collision,
                self.drive(),
                wire[index],
            )
            await until(start + (index + 1) * BIT)
        error_start = start + (collision + 1) * BIT
        self.sender = 1
        await Timer(1, unit="ps")
        assert self.drive() == int(passive), (passive, "flag start", self.drive())
        for index in range(6):
            self.sender = 0 if passive_dominant and index in (1, 2) else 1
            await until(error_start + index * BIT + BIT * 3 // 4)
            assert self.drive() == int(passive), ("flag", index, passive, self.drive())
            await until(error_start + (index + 1) * BIT)
        self.sender = 1
        for index in range(11):
            await until(error_start + (6 + index) * BIT + BIT * 3 // 4)
            assert self.drive() == 1
            await until(error_start + (7 + index) * BIT)
        await Timer(20, unit="ns")
        return {
            "sof_ps": start,
            "flag_start_ps": error_start,
            "intermission_end_ps": error_start + 17 * BIT,
            "passive": passive,
            "bit_error": bit_error,
            "passive_dominant": passive_dominant,
        }


async def setup(dut):
    assert os.environ.get("CAN_FAULT_EXPERIMENT") == "1"
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    bus = FaultPeer(dut)
    cocotb.start_soon(bus.resolve())
    await load_program(
        dut, assemble(Path(__file__).with_name("can_fault_candidate.asm").read_text())
    )
    return PinController(dut, 0x4641554C54), bus


async def counters(controller, ident):
    request = Request(ident, 6, output_limit=3)
    await controller.submit(request, b"")
    output, event = await controller.complete(request, poll_limit=30000)
    assert (
        event.status == 0 and event.output_produced == 3 and event.input_consumed == 0
    )
    assert len(output) == 3 and all(meta == 0 for _, meta in output)
    values = [byte for byte, _ in output]
    return values[0] | values[1] << 8, values[2]


async def fail_once(
    controller, bus, ident, *, tec, rec=0, bit_error=False, passive_dominant=False
):
    passive = tec >= 128 or rec >= 128
    listener = cocotb.start_soon(
        bus.failed_transmission(
            0x321,
            b"\xa5",
            passive=passive,
            bit_error=bit_error,
            passive_dominant=passive_dominant,
        )
    )
    request = Request(ident, 2, arguments_length=3, input_count=1)
    await controller.submit(request, b"\xa5", b"\x03\x21\x01")
    output, event = await controller.complete(request, poll_limit=100000)
    record = await listener
    next_tec = tec + (8 if not passive or bit_error or passive_dominant else 0)
    assert output == [] and event.status == (
        26 if next_tec >= 256 else (21 if bit_error else 24)
    ), event
    assert (
        event.input_consumed == 1 and event.output_produced == 0 and event.detail == 1
    )
    assert await controller.read(0x101) == 0
    assert await counters(controller, ident + 1000) == (next_tec, rec)
    bus.oracle_tec = next_tec
    record["tec_before"] = tec
    record["tec_after"] = next_tec
    return next_tec, record


async def good_tx(controller, bus, ident, *, expected_tec):
    listener = cocotb.start_soon(bus.listen(0x123, b"\x5a"))
    request = Request(ident, 2, arguments_length=3, input_count=1)
    await controller.submit(request, b"\x5a", b"\x01\x23\x01")
    output, event = await controller.complete(request, poll_limit=50000)
    await listener
    assert output == [] and event.status == 0 and event.detail == 1, event
    assert await counters(controller, ident + 1000) == (expected_tec, 0)


@cocotb.test(timeout_time=45, timeout_unit="ms")
async def test_persistent_passive_ack_exception(dut):
    controller, bus = await setup(dut)
    assert await counters(controller, 0) == (0, 0)
    tec = 0
    records = []
    for index in range(16):
        tec, record = await fail_once(controller, bus, 10 + index, tec=tec)
        records.append(record)
    assert tec == 128
    for index in range(2):
        tec, record = await fail_once(controller, bus, 30 + index, tec=tec)
        records.append(record)
    assert tec == 128 and int(dut.uio_oe.value) == 1
    await good_tx(controller, bus, 40, expected_tec=127)
    tec, record = await fail_once(controller, bus, 41, tec=127)
    assert tec == 135 and not record["passive"]
    records.append(record)
    tec, record = await fail_once(controller, bus, 42, tec=tec, passive_dominant=True)
    assert tec == 143 and record["passive"]
    records.append(record)
    Path("passive_timings.json").write_text(json.dumps(records, indent=2) + "\n")


@cocotb.test(timeout_time=55, timeout_unit="ms")
async def test_bus_off_and_monitored_recovery(dut):
    controller, bus = await setup(dut)
    tec = 0
    records = []
    for index in range(32):
        tec, record = await fail_once(
            controller, bus, 100 + index, tec=tec, bit_error=True
        )
        records.append(record)
    assert tec == 256 and int(dut.uio_oe.value) == 0
    before = len(bus.ack_edges)
    request = Request(150, 2, arguments_length=3, input_count=8)
    await controller.submit(request, b"\xaa" * 8, b"\x01\x23\x08")
    output, event = await controller.complete(request, poll_limit=30000)
    assert output == [] and event.status == 26 and event.input_consumed == 8
    assert int(dut.uio_oe.value) == 0 and len(bus.ack_edges) == before
    recovery = Request(151, 5)
    bus.sender = 0
    await controller.submit(recovery, b"")
    await Timer(3 * BIT, unit="ps")
    bus.sender = 1
    # Four complete11-bit groups and a partial group, then a dominant bit.
    # Completed groups must persist; the partial consecutive run must reset.
    await Timer(49 * BIT, unit="ps")
    bus.sender = 0
    await Timer(BIT, unit="ps")
    bus.sender = 1
    started = int(get_sim_time(unit="ps"))
    await Timer(10.9, unit="ms")
    assert int(dut.uio_oe.value) == 0, "bus-off cleared before the remaining124 groups"
    await with_timeout(ValueChange(dut.uio_oe), 40, "us")
    reenabled = int(get_sim_time(unit="ps"))
    assert 124 * 11 * BIT <= reenabled - started <= 124 * 11 * BIT + 2 * BIT
    output, event = await controller.complete(recovery, poll_limit=50000)
    finished = int(get_sim_time(unit="ps"))
    assert output == [] and event.status == 0 and int(dut.uio_oe.value) == 1
    assert await counters(controller, 1151) == (0, 0)
    await good_tx(controller, bus, 152, expected_tec=0)
    Path("bus_off_timings.json").write_text(
        json.dumps(
            {
                "errors": records,
                "complete_groups_before_interruption": 4,
                "remaining_groups_after_interruption": 124,
                "recovery_reenable_after_last_release_ps": reenabled - started,
                "terminal_after_last_release_ps": finished - started,
            },
            indent=2,
        )
        + "\n"
    )


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_receiver_counts_and_winner_retry_compatibility(dut):
    controller, bus = await setup(dut)
    await rx(controller, bus, 200, 0x123, b"\xa5", corrupt=True)
    assert await counters(controller, 1200) == (0, 1)
    await rx(controller, bus, 201, 0x456, b"\x5a", corrupt=True)
    assert await counters(controller, 1201) == (0, 2)
    await rx(controller, bus, 202, 0x123, b"\xa5")
    assert await counters(controller, 1202) == (0, 1)
    await rx(controller, bus, 203, 0x456, b"\x5a")
    assert await counters(controller, 1203) == (0, 0)
    await winner_request(
        controller,
        bus,
        204,
        0x7FF,
        b"\xaa" * 8,
        [(0x123, bytes(8)), (0x456, b"\x55" * 8)],
    )
    assert await counters(controller, 1204) == (0, 0)
    await winner_request(
        controller,
        bus,
        205,
        0x7FF,
        b"\x55\xaa\xff\x00",
        [(0x123, b"\x12\x34")],
        ack_failures=1,
    )
    assert await counters(controller, 1205) == (7, 0)


@cocotb.test(timeout_time=200, timeout_unit="ms")
async def test_receive_counter_passive_saturation_and_success(dut):
    controller, bus = await setup(dut)
    for index in range(256):
        await rx(controller, bus, 300 + index, 0x123, b"", corrupt=True)
        if (index + 1) % 16 == 0:
            assert await counters(controller, 2000 + index) == (0, min(255, index + 1))
        if index == 127:
            tec, _ = await fail_once(controller, bus, 3000, tec=0, rec=128)
            assert (
                tec == 0
            )  # Passive ACK exception also applies when REC caused passivity.
    assert int(dut.uio_oe.value) == 1, "REC saturation must not cause bus-off"
    await rx(controller, bus, 600, 0x123, b"\x5a")
    assert await counters(controller, 2600) == (0, 127)
    tec, record = await fail_once(controller, bus, 601, tec=0, rec=127)
    assert tec == 8 and not record["passive"]
