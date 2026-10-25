"""UART runtime ABI acceptance on the explicit generic eight-register model."""

import json
import os
import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ValueChange, with_timeout
from cocotb.utils import get_sim_time
from generic_frontier import assemble
from isa_variants import label_addresses
from test_uart_probe import BIT_PS, armed, decode_tx, send_rx

from test import PinController, load_program, reset
from tools.runtime import Completion, Request

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "study/protocol_exploration/uart_runtime_candidate.asm"


async def trace_deadlines(dut, trace):
    labels = label_addresses(CANDIDATE.read_text())
    watched = {
        labels[name]: name
        for name in [
            "start_deadline",
            "search",
            "poll_timeout",
            "false_start_timeout",
            "qualified",
        ]
    }
    pending = False
    while True:
        await ValueChange(dut.user_project.core.pc)
        await Timer(1, unit="ps")
        address = int(dut.user_project.core.pc.value)
        name = watched.get(address)
        if name == "start_deadline":
            pending = True
        elif name == "search" and pending:
            trace.append({"start_ps": int(get_sim_time(unit="ps"))})
            pending = False
        elif name in {"poll_timeout", "false_start_timeout", "qualified"}:
            trace[-1][name + "_ps"] = int(get_sim_time(unit="ps"))


async def setup(dut):
    assert os.environ.get("UART_RUNTIME_EXPERIMENT") == "1", (
        "Use run_uart_runtime.py --expanded-model; production capacity is insufficient"
    )
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    await load_program(dut, assemble(CANDIDATE.read_text()))
    trace = []
    cocotb.start_soon(trace_deadlines(dut, trace))
    return PinController(dut, 0x55415254), trace


async def exchange(
    dut,
    controller,
    ident,
    tx=b"",
    rx=b"",
    *,
    count=None,
    op=None,
    status=0,
    expected=None,
    windows=1,
    **sender_options,
):
    if count is None:
        count = len(rx)
    if op is None:
        op = 3 if tx and count else (2 if count else 1)
    request = Request(
        ident, op, arguments_length=4, input_count=len(tx), output_limit=count
    )
    decoder = cocotb.start_soon(decode_tx(dut, tx)) if tx else None
    await controller.submit(request, tx, bytes([count, windows, 0, 0]))
    if count:
        await armed(controller)
    sender = cocotb.start_soon(send_rx(dut, rx, **sender_options)) if rx else None
    output, event = await controller.complete(request, poll_limit=100000)
    if sender:
        await with_timeout(sender, 100, "ms")
    if decoder:
        await decoder
    if expected is None:
        expected = rx if status == 0 else b""
    assert output == [(b, 0) for b in expected], (event, output, expected)
    assert event.status == status and event.input_consumed == len(tx), event
    assert event.output_produced == len(expected) and event.detail == 0
    assert int(dut.uio_out.value) == 1 and int(dut.uio_oe.value) == 1
    assert await controller.read(0x10E) == 0
    assert await controller.read(0x101) == 0


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_uart_runtime_arbitrary_requests(dut):
    controller, _ = await setup(dut)
    rng = random.Random(0x55415254)
    for length in [0, 1, 2, 63, 64]:
        tx = bytes(rng.randrange(256) for _ in range(length))
        rx = bytes(rng.randrange(256) for _ in range(length))
        await exchange(dut, controller, 3 * length, tx, op=1)
        await exchange(dut, controller, 3 * length + 1, rx=rx, op=2)
        await exchange(dut, controller, 3 * length + 2, tx, rx, op=3)
    await exchange(
        dut, controller, 200, b"\x00\xff\x55\xaa", b"\xaa\x55\xff\x00", windows=255
    )


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_uart_runtime_quiet_clock_deadline(dut):
    controller, trace = await setup(dut)
    for windows in [1, 2, 3]:
        start = len(trace)
        await exchange(
            dut, controller, windows, count=1, op=2, windows=windows, status=6
        )
        record = trace[start]
        clocks = (record["poll_timeout_ps"] - record["start_ps"]) // 20000
        assert clocks == windows * 65536, (windows, clocks, record)
    await exchange(dut, controller, 10, rx=b"\xa5")
    Path("deadline_timings.json").write_text(json.dumps(trace, indent=2) + "\n")


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_uart_runtime_phase_rate_and_partial_failures(dut):
    controller, _ = await setup(dut)
    ident = 300
    for phase in [1, 5000, 10000, 15000, 19999]:
        for rate in [-0.01, 0, 0.01]:
            await exchange(
                dut,
                controller,
                ident,
                rx=b"\x00\xff\x55\xaa\x01\x80\x7f\xfe",
                phase_ps=phase,
                rate_error=rate,
            )
            ident += 1
    await exchange(dut, controller, ident, rx=b"\xa5\x5a", false_start=True)
    await exchange(
        dut,
        controller,
        ident + 1,
        rx=b"\x42\xa5",
        bad_stop=True,
        status=7,
        expected=b"\x42",
    )
    await exchange(
        dut, controller, ident + 2, rx=b"\x7e", count=2, status=6, expected=b"\x7e"
    )
    await exchange(dut, controller, ident + 3, rx=b"\xf9")


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def test_uart_runtime_false_start_storm_and_low_line(dut):
    controller, trace = await setup(dut)
    start = len(trace)
    request = Request(400, 2, arguments_length=4, output_limit=1)
    await controller.submit(request, b"", b"\x01\x01\x00\x00")
    await armed(controller)

    async def storm():
        while True:
            dut.uio_in.value = 0
            await Timer(BIT_PS // 8, unit="ps")
            dut.uio_in.value = 2
            await Timer(2 * BIT_PS - BIT_PS // 8, unit="ps")

    pulses = cocotb.start_soon(storm())
    output, event = await controller.complete(request, poll_limit=100000)
    pulses.cancel()
    dut.uio_in.value = 2
    assert output == [] and event.status == 6, event
    record = trace[start]
    deadline = record.get("poll_timeout_ps", record.get("false_start_timeout_ps"))
    elapsed = (deadline - record["start_ps"]) // 20000
    assert 65536 <= elapsed <= 65536 + 224 and "qualified_ps" not in record, record
    await exchange(dut, controller, 401, rx=b"\xa5")
    # A fresh start that remains low fails framing, then cannot be mistaken
    # for a new start until a subsequent request observes high again.
    request = Request(402, 2, arguments_length=4, output_limit=1)
    await controller.submit(request, b"", b"\x01\x01\x00\x00")
    await armed(controller)
    dut.uio_in.value = 0
    output, event = await controller.complete(request, poll_limit=100000)
    assert output == [] and event.status == 7, event
    await exchange(dut, controller, 403, count=1, op=2, status=6)
    dut.uio_in.value = 2
    await exchange(dut, controller, 404, rx=b"\x5a")
    Path("false_start_timings.json").write_text(json.dumps(trace, indent=2) + "\n")


async def raw_rejection(
    dut, controller, ident, mutate, payload=b"\xa5", arguments=b"\x00\x01\x00\x00"
):
    record = bytearray(
        Request(ident, 1, arguments_length=4, input_count=len(payload)).encode()
    )
    mutate(record)
    await controller.write(0x100, 1)
    for offset, byte in enumerate(arguments):
        await controller.write(offset, byte)
    for byte in payload:
        await controller.write(0x110, byte)
    for byte in record:
        await controller.write(0x120, byte)

    async def no_uart_transition():
        await ValueChange(dut.uio_out)
        raise AssertionError("UART TX activity for rejected request")

    guard = cocotb.start_soon(no_uart_transition())
    await controller.write(0x121, 0)
    for _ in range(10000):
        if await controller.read(0x105):
            break
    else:
        raise AssertionError("Rejected request did not retire")
    assert await controller.read(0x103) == 0
    event = Completion.decode(bytes([await controller.read(0x142) for _ in range(16)]))
    guard.cancel()
    assert event.request_id == ident and event.input_consumed == len(payload), event
    assert event.output_produced == 0 and event.detail == 0, event
    assert await controller.read(0x101) == 0 and await controller.read(0x10E) == 0
    assert int(dut.uio_out.value) == 1 and int(dut.uio_oe.value) == 1
    return event.status


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_uart_runtime_rejects_malformed_requests(dut):
    controller, _ = await setup(dut)
    await Timer(1, unit="us")
    cases = []
    for offset in [3, 5, 7, 9, 11, 12, 13, 14, 15]:
        cases.append((offset, 1, b"\x00\x01\x00\x00", 1))
    for op in [0, 4, 255]:
        cases.append((2, op, b"\x00\x01\x00\x00", 2))
    for offset, value in [(4, 1), (4, 128), (6, 0), (6, 3), (6, 5)]:
        cases.append((offset, value, b"\x00\x01\x00\x00", 3))
    for args in [b"\x00\x00\x00\x00", b"\x00\x01\x01\x00", b"\x00\x01\x00\xa5"]:
        cases.append((2, 1, args, 3))
    for offset, value, args in [
        (8, 0, b"\x00\x01\x00\x00"),
        (8, 2, b"\x00\x01\x00\x00"),
        (10, 65, b"\x00\x01\x00\x00"),
        (10, 1, b"\x00\x01\x00\x00"),
        (2, 2, b"\x00\x01\x00\x00"),
        (2, 1, b"\x01\x01\x00\x00"),
        (2, 3, b"\x41\x01\x00\x00"),
        (2, 3, b"\x02\x01\x00\x00"),
    ]:
        cases.append((offset, value, args, 4))
    for ident, (offset, value, args, expected) in enumerate(cases, start=500):
        status = await raw_rejection(
            dut,
            controller,
            ident,
            lambda record, o=offset, v=value: record.__setitem__(o, v),
            arguments=args,
        )
        assert status == expected, (ident, status, expected)
    await exchange(dut, controller, 550, b"\x00\xff", b"\x55\xaa")


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def test_uart_runtime_reset_during_tx_and_rx(dut):
    controller, _ = await setup(dut)
    for direction in ["TX", "RX"]:
        if direction == "TX":
            request = Request(600, 1, arguments_length=4, input_count=64)
            await controller.submit(request, bytes(range(64)), b"\x00\x01\x00\x00")
            await Timer(2 * BIT_PS, unit="ps")
        else:
            request = Request(601, 2, arguments_length=4, output_limit=1)
            await controller.submit(request, b"", b"\x01\x01\x00\x00")
            await armed(controller)
            dut.uio_in.value = 0
            await Timer(3 * BIT_PS, unit="ps")
        dut.rst_n.value = 0
        await RisingEdge(dut.clk)
        await Timer(1, unit="ps")
        assert int(dut.uio_oe.value) == 0
        await reset(dut, pin_input=2)
        await load_program(dut, assemble(CANDIDATE.read_text()))
        controller = PinController(dut, 0x600)
        await exchange(dut, controller, 602, b"\xa5", b"\x5a")
