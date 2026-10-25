"""Independent pin peers for the compact UART exploration image.

This covers valid runtime envelopes and line-level failures. It deliberately
does not claim the unimplemented request validation or clock-deadline ABI of
the final UART runtime milestone.
"""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import (
    RisingEdge,
    SimTimeoutError,
    Timer,
    ValueChange,
    with_timeout,
)
from cocotb.utils import get_sim_time

from test import PinController, firmware, load_program, reset
from tools.runtime import Request

BIT_PS = 434 * 20_000


async def check_tx_edges(dut, byte, start_ps):
    frame = [0] + [(byte >> bit) & 1 for bit in range(8)] + [1]
    for index in range(1, len(frame)):
        if frame[index] != frame[index - 1]:
            await ValueChange(dut.uio_out)
            assert get_sim_time(unit="ps") == start_ps + index * BIT_PS
            assert int(dut.uio_out.value) == frame[index]
    remaining = start_ps + 10 * BIT_PS - 1 - get_sim_time(unit="ps")
    try:
        await with_timeout(ValueChange(dut.uio_out), remaining, "ps")
    except SimTimeoutError:
        return
    raise AssertionError("unexpected UART transition before the stop bit ended")


async def decode_tx(dut, payload):
    """Decode at the peer's bit centers, without reading core state."""
    for expected in payload:
        while True:
            await ValueChange(dut.uio_out)
            if not int(dut.uio_out.value) & 1:
                break
        edges = cocotb.start_soon(
            check_tx_edges(dut, expected, get_sim_time(unit="ps"))
        )
        await Timer(BIT_PS // 2, unit="ps")
        assert int(dut.uio_oe.value) == 1
        assert int(dut.uio_out.value) == 0, "invalid start bit"
        value = 0
        for bit in range(8):
            await Timer(BIT_PS, unit="ps")
            assert int(dut.uio_oe.value) == 1
            value |= (int(dut.uio_out.value) & 1) << bit
        await Timer(BIT_PS, unit="ps")
        assert int(dut.uio_out.value) == 1, "invalid stop bit"
        assert value == expected, (hex(value), hex(expected))
        # Return to edge detection before a next frame can start.
        await Timer(BIT_PS // 2 - 20_000, unit="ps")
        await edges


async def send_rx(
    dut, payload, *, rate_error=0, phase_ps=1, bad_stop=False, false_start=False
):
    bit_ps = round(BIT_PS / (1 + rate_error))
    await RisingEdge(dut.clk)
    await Timer(phase_ps, unit="ps")
    if false_start:
        dut.uio_in.value = 0
        await Timer(bit_ps // 8, unit="ps")
        dut.uio_in.value = 2
        await Timer(2 * bit_ps, unit="ps")
    for index, byte in enumerate(payload):
        bits = [0] + [(byte >> bit) & 1 for bit in range(8)]
        bits += [0 if bad_stop and index == len(payload) - 1 else 1]
        for bit in bits:
            dut.uio_in.value = bit << 1
            await Timer(bit_ps, unit="ps")
    dut.uio_in.value = 2


async def armed(controller):
    for _ in range(30_000):
        if await controller.read(0x10E) == 0xA5:
            # The peer observes the documented receive arming interval.
            await Timer(2 * BIT_PS, unit="ps")
            return
    raise AssertionError("UART did not arm reception")


async def exchange(
    dut,
    controller,
    ident,
    tx,
    rx,
    *,
    requested=None,
    status=0,
    expected=None,
    **sender_options,
):
    count = len(rx) if requested is None else requested
    op = 3 if tx and count else (2 if count else 1)
    request = Request(
        ident, op, arguments_length=4, input_count=len(tx), output_limit=count
    )
    decoder = cocotb.start_soon(decode_tx(dut, tx)) if tx else None
    await controller.submit(request, tx, bytes([count, 1, 0, 0]))
    if count:
        await armed(controller)
    sender = cocotb.start_soon(send_rx(dut, rx, **sender_options)) if rx else None
    output, completion = await controller.complete(request, poll_limit=100_000)
    if sender:
        await with_timeout(sender, 100, "ms")
    if decoder:
        await with_timeout(decoder, 100, "ms")
    assert output == [(byte, 0) for byte in (rx if expected is None else expected)]
    assert completion.status == status
    assert completion.input_consumed == len(tx)
    assert completion.output_produced == len(output)
    assert completion.detail == 0
    assert await controller.read(0x101) == 0
    assert int(dut.uio_out.value) == 1
    assert int(dut.uio_oe.value) == 1


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    await load_program(dut, firmware("uart_probe.asm"))
    return PinController(dut)


@cocotb.test(timeout_time=250, timeout_unit="ms")
async def test_uart_probe_arbitrary_tx_rx(dut):
    controller = await setup(dut)
    rng = random.Random(0x55415254)
    for index, length in enumerate([0, 1, 2, 63, 64, 0, 1, 8]):
        tx = bytes(rng.randrange(256) for _ in range(length))
        if length >= 4:
            tx = b"\x00\xff\x55\xaa" + tx[4:]
        rx = bytes(rng.randrange(256) for _ in range(length))
        await exchange(dut, controller, 100 + index, tx, rx)
    # Separate TX-only and RX-only requests exercise the zero-length paths.
    await exchange(dut, controller, 200, bytes(range(64)), b"")
    await exchange(dut, controller, 201, b"", bytes(range(64)))


@cocotb.test(timeout_time=250, timeout_unit="ms")
async def test_uart_probe_phase_and_clock_mismatch(dut):
    controller = await setup(dut)
    ident = 300
    for phase_ps in [1, 5_000, 10_000, 15_000, 19_999]:
        for rate_error in [-0.01, 0, 0.01]:
            await exchange(
                dut,
                controller,
                ident,
                b"",
                b"\x00\xff\x55\xaa",
                phase_ps=phase_ps,
                rate_error=rate_error,
            )
            ident += 1


@cocotb.test(timeout_time=250, timeout_unit="ms")
async def test_uart_probe_line_errors_and_recovery(dut):
    controller = await setup(dut)
    await exchange(dut, controller, 500, b"", b"\x34\x12", false_start=True)
    await exchange(
        dut,
        controller,
        501,
        b"",
        b"\xa5\x5a",
        bad_stop=True,
        expected=b"\xa5",
        status=7,
    )
    await exchange(dut, controller, 502, b"", b"", requested=1, expected=b"", status=6)
    await exchange(
        dut, controller, 503, b"", b"\x81", requested=2, expected=b"\x81", status=6
    )
    await exchange(dut, controller, 504, b"\x5a", b"\xc3")
