"""Independent drift/phase stimulus and CAN firmware receive timing checks."""

import json
import os
from itertools import pairwise
from pathlib import Path

import cocotb
from can_peer import frame
from can_recovery_peer import until
from can_winner_peer import ArbitrationPeer, winner_request
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ValueChange
from cocotb.utils import get_sim_time
from frontier_peer import rx, tx
from generic_frontier import assemble
from isa_variants import label_addresses

from test import PinController, load_program, reset
from tools.runtime import Request


class DriftPeer(ArbitrationPeer):
    async def trace_samples(self, source):
        labels = label_addresses(source)
        core = self.dut.user_project.core
        while True:
            await ValueChange(core.pc)
            await Timer(1, unit="ps")
            if int(core.pc.value) == labels["rx_sample"]:
                while int(core.wait_count.value):
                    await RisingEdge(self.dut.clk)
                    await Timer(1, unit="ps")
                await RisingEdge(self.dut.clk)
                self.samples.append(int(get_sim_time(unit="ps")))

    async def drifting_frame(
        self, identifier, data, *, ppm=0, phase_ns=1, jumps=False, crc_error=False
    ):
        wire, ack, _ = frame(identifier, data, crc_error=crc_error)
        bit_ps = round(8_000_000 / (1 + ppm / 1_000_000))
        await Timer(phase_ns, unit="ns")
        start = int(get_sim_time(unit="ps"))
        offset = 0
        boundaries = []
        changes = []
        for index, bit in enumerate(wire):
            if (
                jumps
                and index > 20
                and index < ack - 4
                and wire[index - 1] == 1
                and bit == 0
            ):
                offset = 400_000 if offset == 0 else 0
                changes.append(index)
            boundaries.append(start + index * bit_ps + offset)
        boundaries.append(start + len(wire) * bit_ps + offset)
        edge_start = len(self.ack_edges)
        for index, bit in enumerate(wire):
            await until(boundaries[index])
            self.sender = bit
            await until(
                boundaries[index] + (boundaries[index + 1] - boundaries[index]) * 3 // 4
            )
            assert self.drive() == int(index != ack or crc_error), (
                index,
                ack,
                self.drive(),
                ppm,
            )
        await until(boundaries[-1])
        self.sender = 1
        await Timer(20, unit="ns")
        edges = self.ack_edges[edge_start:]
        if not crc_error:
            assert len(edges) == 2 and [value for _, value in edges] == [0, 1], edges
            assert edges[1][0] - edges[0][0] == 8000, edges
        else:
            assert edges == [], edges
        return {
            "identifier": identifier,
            "dlc": len(data),
            "ppm": ppm,
            "phase_ns": phase_ns,
            "bit_ps": bit_ps,
            "phase_jump_wire_bits": changes,
            "boundaries_ps": boundaries,
            "ack_wire_bit": ack,
            "ack_edges_ns": edges,
        }


async def setup(dut):
    assert os.environ.get("CAN_RESYNC_EXPERIMENT") == "1"
    source = Path(os.environ["CAN_RESYNC_SOURCE"]).read_text()
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    bus = DriftPeer(dut)
    cocotb.start_soon(bus.resolve())
    await load_program(dut, assemble(source))
    cocotb.start_soon(bus.trace_samples(source))
    return PinController(dut, 0x5253594E43), bus


async def receive(controller, bus, ident, identifier, data, **kwargs):
    request = Request(ident, 1, output_limit=11)
    await controller.submit(request, b"")
    await Timer(110, unit="us")
    sample_start = len(bus.samples)
    listener = cocotb.start_soon(bus.drifting_frame(identifier, data, **kwargs))
    output, event = await controller.complete(request, poll_limit=50000)
    record = await listener
    corrupt = kwargs.get("crc_error", False)
    expected = (
        []
        if corrupt
        else [
            (byte, 0)
            for byte in bytes([identifier >> 8, identifier & 255, len(data)]) + data
        ]
    )
    assert output == expected and event.status == (16 if corrupt else 0), (
        event,
        output,
    )
    assert event.input_consumed == 0 and event.output_produced == len(expected)
    assert await controller.read(0x101) == 0 and bus.drive() == 1
    samples = bus.samples[sample_start:]
    record["samples_ps"] = samples
    record["sample_period_clocks"] = [
        (right - left) // 20_000 for left, right in pairwise(samples)
    ]
    # Measurement only: the peer's own bit boundaries supply the expected data.
    if not corrupt:
        assert len(samples) == record["ack_wire_bit"], (
            len(samples),
            record["ack_wire_bit"],
        )
        positions = [
            (sample - begin) / (end - begin)
            for sample, begin, end in zip(
                samples, record["boundaries_ps"], record["boundaries_ps"][1:]
            )
        ]
        assert all(0 < position < 1 for position in positions), positions
        record["sample_phase_min"] = min(positions)
        record["sample_phase_max"] = max(positions)
    return record


@cocotb.test(timeout_time=15, timeout_unit="ms")
async def test_clock_drift_regression(dut):
    controller, bus = await setup(dut)
    records = []
    for ident, ppm in enumerate([5000, -5000, 0]):
        records.append(
            await receive(
                controller,
                bus,
                ident,
                0x6A5,
                b"\x00\xff\x55\xaa\x01\x80\x00\xff",
                ppm=ppm,
            )
        )
    Path("drift_timings.json").write_text(json.dumps(records, indent=2) + "\n")


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_phase_steps_lengths_and_recovery(dut):
    controller, bus = await setup(dut)
    records = []
    for length in range(9):
        records.append(
            await receive(
                controller,
                bus,
                20 + length,
                0 if length % 2 else 0x7FF,
                bytes([0xA5 ^ length] * length),
                phase_ns=[1, 5, 10, 15, 19][length % 5],
                jumps=True,
                ppm=5000 if length % 2 else -5000,
            )
        )
    await receive(
        controller, bus, 40, 0x123, b"\xa5" * 8, crc_error=True, ppm=5000, jumps=True
    )
    records.append(await receive(controller, bus, 41, 0x456, b"\x5a", jumps=True))
    Path("phase_timings.json").write_text(json.dumps(records, indent=2) + "\n")


@cocotb.test(timeout_time=35, timeout_unit="ms")
async def test_resync_image_winner_and_tx_compatibility(dut):
    controller, bus = await setup(dut)
    await tx(controller, bus, 50, 0x123, b"\xff" * 8)
    await rx(controller, bus, 51, 0x456, b"\x5a" * 8)
    await winner_request(
        controller,
        bus,
        52,
        0x7FF,
        b"\xaa" * 8,
        [(0x123, bytes(8)), (0x456, b"\x55" * 8)],
    )
    await winner_request(
        controller,
        bus,
        53,
        0x7FF,
        b"\x55\xaa\xff\x00",
        [(0x123, b"\x12\x34")],
        ack_failures=1,
    )
