"""Independent RXD fault injection for active CAN error-flag bit monitoring.

An ordinary wired-dominant peer cannot turn a transmitted dominant bit into a
recessive observation. This models a disconnected dominant driver/RXD fault at
an external transceiver, without changing the ASIC's commanded TXD.
"""

import json
import os
from pathlib import Path

import can_postflag_peer as previous
import cocotb
from can_fault_equal_peer import counters, good_tx
from can_peer import frame
from can_recovery_peer import BIT, until
from can_rx_flags_peer import receive_good
from cocotb.clock import Clock
from cocotb.triggers import Timer, with_timeout
from cocotb.utils import get_sim_time
from generic_call_frontier import assemble

from test import PinController, load_program, reset
from tools.runtime import Request


class FlagBitPeer(previous.PostflagPeer):
    observed_override = None

    async def resolve(self):
        while True:
            drive = self.drive()
            if drive != self.last_drive:
                self.ack_edges.append((get_sim_time(unit="ns"), drive))
                self.last_drive = drive
            observed = (
                self.sender & drive
                if self.observed_override is None
                else self.observed_override
            )
            self.dut.uio_in.value = observed << 1
            await Timer(10, unit="ns")

    async def flag_bit_fault(self, *, receiver, fault_cell, passive=False):
        wire, ack, _ = frame(0x123 if receiver else 0x321, b"\xa5", crc_error=receiver)
        collision = (
            ack + 1 if receiver else next(i for i in range(20, ack - 2) if wire[i] == 1)
        )
        start = (
            int(get_sim_time(unit="ps"))
            if receiver
            else await with_timeout(self.sof(), 2, "ms")
        )
        for index in range(collision + 1):
            self.sender = wire[index] if receiver else int(index != collision)
            await until(start + index * BIT + BIT * 3 // 4)
            assert self.drive() == (1 if receiver else wire[index])
            await until(start + (index + 1) * BIT)
        flag_start = start + (collision + 1) * BIT
        self.sender = 1
        cells = 6 if passive else fault_cell + 7
        before = len(self.ack_edges)
        for index in range(cells):
            # Force recessive RXD despite commanded dominant TXD for one full
            # cell. Other samples use the actual public wired-dominant pins.
            self.observed_override = 1 if index == fault_cell and not passive else None
            if passive:
                self.sender = 0  # Dominance is explicitly exempt in passive flags.
            await until(flag_start + index * BIT + BIT * 3 // 4)
            assert self.drive() == int(passive), (index, passive, self.drive())
            await until(flag_start + (index + 1) * BIT)
        self.observed_override = None
        self.sender = 1
        for index in range(11):
            await until(flag_start + (cells + index) * BIT + BIT * 3 // 4)
            assert self.drive() == 1, ("delimiter", index, self.drive())
            await until(flag_start + (cells + index + 1) * BIT)
        return {
            "receiver": receiver,
            "fault_cell": fault_cell,
            "passive": passive,
            "flag_start_ps": flag_start,
            "flag_cells": cells,
            "intermission_end_ps": flag_start + (cells + 11) * BIT,
            "commanded_edges_ns": self.ack_edges[before:],
        }


async def setup(dut):
    assert os.environ.get("CAN_FLAG_BIT_EXPERIMENT") == "1"
    source = Path(os.environ["CAN_FLAG_BIT_SOURCE"]).read_text()
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    bus = FlagBitPeer(dut)
    bus.delimiter_samples = []
    cocotb.start_soon(bus.resolve())
    await load_program(dut, assemble(source))
    cocotb.start_soon(bus.delimiter_trace(source))
    cocotb.start_soon(bus.trace_samples(source))
    return PinController(dut, 0x464C4147424954), bus


async def exchange(
    controller, bus, ident, *, receiver, cell, tec=0, rec=0, passive=False
):
    request = Request(
        ident,
        1 if receiver else 2,
        arguments_length=0 if receiver else 3,
        input_count=0 if receiver else 1,
        output_limit=11 if receiver else 0,
    )
    task = None
    if not receiver:
        task = cocotb.start_soon(
            bus.flag_bit_fault(receiver=False, fault_cell=cell, passive=passive)
        )
    await controller.submit(
        request, b"" if receiver else b"\xa5", b"" if receiver else b"\x03\x21\x01"
    )
    if receiver:
        await Timer(110, unit="us")
        task = cocotb.start_soon(
            bus.flag_bit_fault(receiver=True, fault_cell=cell, passive=passive)
        )
    output, event = await controller.complete(request, poll_limit=100000)
    finished = int(get_sim_time(unit="ps"))
    row = await task
    assert output == [] and event.status == (16 if receiver else 21), (event, row)
    assert event.input_consumed == request.input_count and event.output_produced == 0
    assert event.detail == int(not receiver)
    assert finished >= row["intermission_end_ps"] - 1000
    expected = (
        (tec, min(255, rec + 1 + (0 if passive else 8)))
        if receiver
        else (tec + 8 + (0 if passive else 8), rec)
    )
    actual = await counters(controller, ident + 10000)
    assert actual == expected, {
        "actual_counters": actual,
        "expected_counters": expected,
        **row,
    }
    return expected, row


@cocotb.test(timeout_time=35, timeout_unit="ms")
async def test_receiver_active_flag_bit_errors(dut):
    controller, bus = await setup(dut)
    rec = 0
    rows = []
    for cell in range(6):
        (_, rec), row = await exchange(
            controller, bus, 10 + cell, receiver=True, cell=cell, rec=rec
        )
        rows.append(row)
    assert rec == 54
    await receive_good(controller, bus, 30, 0x456, b"\x5a")
    assert await counters(controller, 10030) == (0, 53)
    Path("receiver_flag_bit_timings.json").write_text(json.dumps(rows, indent=2) + "\n")


@cocotb.test(timeout_time=35, timeout_unit="ms")
async def test_transmitter_active_flag_bit_errors(dut):
    controller, bus = await setup(dut)
    tec = 0
    rows = []
    for cell in range(6):
        (tec, _), row = await exchange(
            controller, bus, 50 + cell, receiver=False, cell=cell, tec=tec
        )
        rows.append(row)
    assert tec == 96
    await good_tx(controller, bus, 70, expected_tec=95)
    Path("transmitter_flag_bit_timings.json").write_text(
        json.dumps(rows, indent=2) + "\n"
    )


@cocotb.test(timeout_time=45, timeout_unit="ms")
async def test_passive_flag_dominance_is_not_bit_error(dut):
    controller, bus = await setup(dut)
    tec = rec = 0
    # Eight prolonged-run transactions reach REC136 using the prior independent
    # oracle, not a private RAM write. Dominance throughout a passive flag is
    # six equal samples and must not charge the active-flag bit-error rule.
    for index in range(8):
        tec, rec, _ = await previous.exchange_error(
            controller, bus, 100 + index, tec, rec, [0] * 8
        )
    assert rec == 136
    (_, rec), _ = await exchange(
        controller, bus, 120, receiver=True, cell=2, rec=rec, passive=True
    )
    assert rec == 137
    (tec, _), _ = await exchange(
        controller, bus, 121, receiver=False, cell=2, rec=rec, passive=True
    )
    assert tec == 8 and await counters(controller, 10121) == (8, 137)
