"""Independent CAN ACK-error, overlapping flag and bounded-retry peer."""

import json
import os
import random
from pathlib import Path

import cocotb
from can_peer import frame
from can_tx_peer import Receiver
from cocotb.clock import Clock
from cocotb.triggers import SimTimeoutError, Timer, ValueChange, with_timeout
from cocotb.utils import get_sim_time
from frontier_peer import rx, tx
from generic_frontier import assemble

from test import PinController, load_program, reset
from tools.runtime import Request

BIT = 8_000_000  # ps;125kbit/s


async def until(when):
    remaining = when - int(get_sim_time(unit="ps"))
    if remaining > 0:
        await Timer(remaining, unit="ps")


class RecoveryPeer(Receiver):
    async def retries(
        self, identifier, payload, acknowledgments, *, echo_bits=1, stuck=False
    ):
        wire, ack, _ = frame(identifier, payload)
        records = []
        expected_next = None
        for attempt, acknowledge in enumerate(acknowledgments, 1):
            while self.drive() != 0:
                await ValueChange(self.dut.uio_out)
                await Timer(1, unit="ps")
            start = int(get_sim_time(unit="ps"))
            if expected_next is not None:
                assert abs(start - expected_next) <= 1000, (start, expected_next)
            for index in range(ack + 1):
                self.sender = int(not (acknowledge and index == ack))
                await until(start + index * BIT + BIT * 3 // 4)
                assert self.drive() == wire[index], (
                    attempt,
                    index,
                    self.drive(),
                    wire[index],
                )
                await until(start + (index + 1) * BIT)
            self.sender = 1
            record = {"attempt": attempt, "sof_ps": start, "acknowledged": acknowledge}
            if acknowledge:
                for index in range(ack + 1, len(wire)):
                    await until(start + index * BIT + BIT * 3 // 4)
                    assert self.drive() == 1
                    await until(start + (index + 1) * BIT)
                record["completion_earliest_ps"] = start + len(wire) * BIT
                records.append(record)
                break
            error_start = start + (ack + 1) * BIT
            await Timer(1, unit="ps")
            assert self.drive() == 0, (
                "active flag did not begin at ACK delimiter boundary"
            )
            for index in range(6 + echo_bits):
                self.sender = 0 if (echo_bits and index >= 1) else 1
                await until(error_start + index * BIT + BIT * 3 // 4)
                assert self.drive() == int(index >= 6), (index, self.drive())
                await until(error_start + (index + 1) * BIT)
            await Timer(11, unit="ns")  # Let the10ns public resolver observe release.
            edges = [(round(when * 1000), value) for when, value in self.ack_edges]
            # The public bus resolver observes pins every10ns; SOF wakeup adds1ps.
            # Require both boundaries within that observation quantum, far below
            # one20ns core clock or one8us CAN cell.
            observed = []
            for boundary, value in [(error_start, 0), (error_start + 6 * BIT, 1)]:
                matches = [
                    when
                    for when, level in edges
                    if abs(when - boundary) <= 10_001 and level == value
                ]
                assert len(matches) == 1, (boundary, value, edges)
                observed.append(matches[0])
            record.update(
                {
                    "active_flag_start_ps": error_start,
                    "active_flag_clocks": 2400,
                    "observed_flag_edges_ps": observed,
                    "observed_flag_clocks": (observed[1] - observed[0]) / 20_000,
                    "echo_extension_bits": echo_bits,
                }
            )
            if stuck:
                self.sender = 0
                await Timer(35 * BIT, unit="ps")
                assert self.drive() == 1
                self.sender = 1
                records.append(record)
                break
            self.sender = 1
            idle_start = error_start + (6 + echo_bits) * BIT
            for index in range(11):  # 8 delimiter +3 intermission cells
                await until(idle_start + index * BIT + BIT * 3 // 4)
                assert self.drive() == 1, (
                    "delimiter/intermission",
                    index,
                    self.drive(),
                )
                await until(idle_start + (index + 1) * BIT)
            expected_next = idle_start + 11 * BIT
            record["next_sof_expected_ps"] = expected_next
            record["completion_earliest_ps"] = expected_next
            records.append(record)
        self.sender = 1
        # Completion must not be followed by an unexpected fourth attempt.
        try:
            await with_timeout(ValueChange(self.dut.uio_out), 2 * BIT, "ps")
        except SimTimeoutError:
            return records
        raise AssertionError("Unexpected output transition after final attempt")


async def setup(dut):
    assert os.environ.get("CAN_RECOVERY_EXPERIMENT") == "1"
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    bus = RecoveryPeer(dut)
    cocotb.start_soon(bus.resolve())
    await load_program(
        dut,
        assemble(Path(__file__).with_name("can_recovery_candidate.asm").read_text()),
    )
    return PinController(dut, 0x43414E), bus


async def retry_request(
    controller,
    bus,
    ident,
    identifier,
    data,
    acknowledgments,
    *,
    status=0,
    echo_bits=1,
    stuck=False,
):
    listener = cocotb.start_soon(
        bus.retries(identifier, data, acknowledgments, echo_bits=echo_bits, stuck=stuck)
    )
    request = Request(ident, 3, arguments_length=3, input_count=len(data))
    await controller.submit(
        request, data, bytes([identifier >> 8, identifier & 255, len(data)])
    )
    output, event = await controller.complete(request, poll_limit=100000)
    completed_at = int(get_sim_time(unit="ps"))
    records = await listener
    assert (
        output == [] and event.status == status and event.detail == len(acknowledgments)
    ), event
    assert event.input_consumed == len(data) and event.output_produced == 0
    if not stuck:
        assert completed_at >= records[-1]["completion_earliest_ps"] - 1_000, records[
            -1
        ]
    assert await controller.read(0x101) == 0 and bus.drive() == 1
    return records


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_ack_error_flag_and_bounded_retry(dut):
    controller, bus = await setup(dut)
    rng = random.Random(0x5245545259)
    timings = []
    for length in range(9):
        acknowledgments = [False, True] if length % 2 else [False, False, True]
        timings += await retry_request(
            controller,
            bus,
            length,
            rng.randrange(2048),
            bytes(rng.randrange(256) for _ in range(length)),
            acknowledgments,
        )
    timings += await retry_request(
        controller, bus, 20, 0, bytes(8), [False, True], echo_bits=0
    )
    timings += await retry_request(
        controller, bus, 21, 0x7FF, b"\xff" * 8, [False, True], echo_bits=3
    )
    Path("retry_timings.json").write_text(json.dumps(timings, indent=2) + "\n")


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_retry_exhaustion_and_dominant_recovery_timeout(dut):
    controller, bus = await setup(dut)
    await retry_request(controller, bus, 30, 0x321, b"\xa5", [False] * 3, status=24)
    await rx(controller, bus, 31, 0x123, b"\x5a")
    await retry_request(
        controller, bus, 32, 0x321, b"\xa5", [False], status=25, stuck=True, echo_bits=0
    )
    await rx(controller, bus, 33, 0x456, b"\xa5")
    await retry_request(controller, bus, 34, 0x123, b"\x55\xaa", [True])


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_recovery_image_legacy_modes(dut):
    controller, bus = await setup(dut)
    await tx(controller, bus, 40, 0x123, b"\xa5")
    await rx(controller, bus, 41, 0x456, b"\x5a")
    await tx(controller, bus, 42, 0x321, b"\xff" * 8, ack=False, status=24)
    await rx(controller, bus, 43, 0x123, b"\xa5", corrupt=True)
    await tx(controller, bus, 44, 0x7FF, b"\x55", winner=0x3FF, status=22)
    await retry_request(controller, bus, 45, 0x456, b"\x5a", [False, True])
