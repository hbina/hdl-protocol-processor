"""Independent CAN frame-ending, overload and early-next-SOF wire checks."""

import json
import os
import random
from pathlib import Path

import cocotb
from can_fault_equal_peer import counters
from can_peer import frame
from can_recovery_peer import BIT, until
from can_rx_flags_peer import ReceivePeer
from cocotb.clock import Clock
from cocotb.triggers import Timer
from cocotb.utils import get_sim_time
from generic_call_frontier import assemble

from test import PinController, load_program, reset
from tools.runtime import Request


class TailPeer(ReceivePeer):
    async def tail_frame(self, identifier, data, kind):
        wire, ack, _ = frame(identifier, data)
        changed = {
            "last_eof": ack + 8,
            "first_intermission": ack + 9,
            "second_intermission": ack + 10,
            "third_intermission": ack + 11,
        }.get(kind)
        if changed is not None:
            wire[changed] = 0
        start = int(get_sim_time(unit="ps"))
        limit = (
            changed + 1
            if kind in {"first_intermission", "second_intermission"}
            else len(wire)
        )
        edges = len(self.ack_edges)
        for index, bit in enumerate(wire[:limit]):
            self.sender = bit
            await until(start + index * BIT + BIT * 3 // 4)
            assert self.drive() == int(index != ack), (kind, index, ack, self.drive())
            await until(start + (index + 1) * BIT)
        overload_start = None
        if kind in {"first_intermission", "second_intermission"}:
            overload_start = start + limit * BIT
            self.sender = 1
            for index in range(17):
                await until(overload_start + index * BIT + BIT * 3 // 4)
                assert self.drive() == int(index >= 6), (
                    "overload flag/delimiter",
                    kind,
                    index,
                    self.drive(),
                )
                await until(overload_start + (index + 1) * BIT)
        if kind == "third_intermission":
            # The changed bit is the following frame's SOF. The current ABI
            # captures one frame; observe its service gap explicitly rather
            # than silently claiming continuous-node reception.
            successor, successor_ack, _ = frame(0x456, b"\xa5")
            successor_start = start + changed * BIT
            for index in range(1, len(successor)):
                self.sender = successor[index]
                await until(successor_start + index * BIT + BIT * 3 // 4)
                assert self.drive() == 1, ("unexpected next-frame drive", index)
                await until(successor_start + (index + 1) * BIT)
            successor_ack_time = successor_start + successor_ack * BIT
        else:
            successor_ack_time = None
        self.sender = 1
        return {
            "kind": kind,
            "identifier": identifier,
            "payload": list(data),
            "changed_wire_bit": changed,
            "ack_wire_bit": ack,
            "frame_start_ps": start,
            "overload_start_ps": overload_start,
            "successor_unacknowledged_at_ps": successor_ack_time,
            "commanded_edges_ns": self.ack_edges[edges:],
        }


async def setup(dut):
    assert os.environ.get("CAN_TAIL_EXPERIMENT") == "1"
    source = Path(os.environ["CAN_TAIL_SOURCE"]).read_text()
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    bus = TailPeer(dut)
    cocotb.start_soon(bus.resolve())
    await load_program(dut, assemble(source))
    return PinController(dut, 0x5441494C), bus


async def receive(controller, bus, ident, identifier, data, kind):
    request = Request(ident, 1, output_limit=11)
    await controller.submit(request, b"")
    await Timer(110, unit="us")
    task = cocotb.start_soon(bus.tail_frame(identifier, data, kind))
    output, event = await controller.complete(request, poll_limit=100000)
    row = await task
    expected = [
        (byte, 0) for byte in [identifier >> 8, identifier & 255, len(data), *data]
    ]
    assert event.status == 0 and output == expected, (event, output, expected, row)
    assert (
        event.input_consumed == 0
        and event.output_produced == len(expected)
        and event.detail == 0
    )
    assert await counters(controller, ident + 10000) == (0, 0)
    return row


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_last_eof_dominant_acceptance(dut):
    controller, bus = await setup(dut)
    rng = random.Random(0x454F46)
    rows = []
    for index, length in enumerate([0, 1, 8]):
        payload = bytes(rng.randrange(256) for _ in range(length))
        rows.append(
            await receive(
                controller, bus, 10 + index, rng.randrange(2048), payload, "last_eof"
            )
        )
    await receive(controller, bus, 20, 0x123, b"\x5a", "normal")
    Path("last_eof_timings.json").write_text(json.dumps(rows, indent=2) + "\n")


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_intermission_overload(dut):
    controller, bus = await setup(dut)
    rows = []
    for index, kind in enumerate(["first_intermission", "second_intermission"]):
        rows.append(await receive(controller, bus, 30 + index, 0x321, b"\xa5", kind))
    await receive(controller, bus, 40, 0x123, b"\x5a", "normal")
    Path("overload_timings.json").write_text(json.dumps(rows, indent=2) + "\n")


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_third_intermission_sof_classification(dut):
    controller, bus = await setup(dut)
    row = await receive(controller, bus, 50, 0x123, b"\x5a", "third_intermission")
    assert row["successor_unacknowledged_at_ps"] is not None
    await receive(controller, bus, 51, 0x321, b"\xa5", "normal")
    Path("third_intermission_timings.json").write_text(json.dumps(row, indent=2) + "\n")


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_normal_frame_tail_control(dut):
    controller, bus = await setup(dut)
    for index, data in enumerate([b"", b"\x5a", b"\x00\xff\x55\xaa\x01\x80\x12\x34"]):
        await receive(controller, bus, 70 + index, 0x123 + index, data, "normal")
