"""Validated JTAG request/length ABI against an independent sixteen-state TAP."""

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import First, Timer, ValueChange
from run_jtag_runtime import candidate_words
from test_jtag_probe import Tap, scan

from test import PinController, load_program, reset
from tools.runtime import Completion, Request


async def setup(dut):
    assert os.environ.get("JTAG_RUNTIME_EXPERIMENT") == "1", (
        "Use run_jtag_runtime.py jtag_runtime --expanded-model"
    )
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut)
    tap = Tap(dut)
    cocotb.start_soon(tap.run())
    await load_program(dut, candidate_words("jtag_runtime"))
    # Initial TAP reset belongs to boot, before per-request rejection checks.
    await Timer(70, unit="us")
    assert tap.state == "idle" and tap.instruction == 1 and tap.resets >= 1
    return PinController(dut, 0x4A544147), tap


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def test_jtag_runtime_scans_and_readback(dut):
    controller, tap = await setup(dut)
    resets = tap.resets
    await scan(dut, controller, tap, 1, False, bytes(4), 32)
    await scan(dut, controller, tap, 2, True, b"\xe2", 5)
    rng = random.Random(0x4A544147)
    for ident, bits in enumerate([1, 7, 8, 9, 31, 32, 33, 511, 512], 10):
        tap.data = rng.getrandbits(32)
        data = bytes(rng.randrange(256) for _ in range((bits + 7) // 8))
        await scan(dut, controller, tap, ident, False, data, bits)
    await scan(dut, controller, tap, 30, False, bytes.fromhex("efbeadde"), 32)
    assert tap.data == 0xDEADBEEF
    await scan(dut, controller, tap, 31, False, bytes(4), 32)
    await scan(dut, controller, tap, 32, True, b"\x1f", 5)
    await scan(dut, controller, tap, 33, False, b"\x55\x01", 9)
    assert tap.resets == resets


async def reject_request(dut, controller, tap, ident, changes, arguments, payload):
    record = bytearray(
        Request(
            ident,
            1,
            arguments_length=2,
            input_count=len(payload),
            output_limit=len(payload),
        ).encode()
    )
    for offset, value in changes.items():
        record[offset] = value
    assert await controller.read(0x101) == 0
    await controller.write(0x100, 1)
    for offset, byte in enumerate(arguments):
        await controller.write(offset, byte)
    for byte in payload:
        await controller.write(0x110, byte)
    for byte in record:
        await controller.write(0x120, byte)
    snapshot = (
        tap.state,
        tap.instruction,
        tap.data,
        len(tap.captures),
        tap.resets,
        tap.last_rise,
    )

    async def stable_pins():
        await First(ValueChange(dut.uio_out), ValueChange(dut.uio_oe))
        raise AssertionError("JTAG pin activity for rejected request")

    guard = cocotb.start_soon(stable_pins())
    await controller.write(0x121, 0)
    for _ in range(10000):
        if await controller.read(0x105):
            break
    else:
        raise AssertionError("Invalid JTAG request did not retire")
    assert await controller.read(0x103) == 0
    event = Completion.decode(bytes([await controller.read(0x142) for _ in range(16)]))
    guard.cancel()
    assert event.request_id == ident and event.input_consumed == len(payload), event
    assert event.output_produced == 0 and event.detail == 0
    assert (
        tap.state,
        tap.instruction,
        tap.data,
        len(tap.captures),
        tap.resets,
        tap.last_rise,
    ) == snapshot
    assert int(dut.uio_out.value) == 0 and int(dut.uio_oe.value) == 7
    assert await controller.read(0x101) == 0
    return event.status


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def test_jtag_runtime_rejects_and_preserves_tap(dut):
    controller, tap = await setup(dut)
    await scan(dut, controller, tap, 100, True, b"\x02", 5)
    cases = []
    for offset in [3, 5, 7, 9, 11, 12, 13, 14, 15]:
        cases.append(({offset: 1}, b"\x00\x08", b"\xa5", 1))
    for op in [0, 2, 255]:
        cases.append(({2: op}, b"\x00\x08", b"\xa5", 2))
    for fields in [{4: 1}, {4: 128}, {6: 0}, {6: 1}, {6: 3}]:
        cases.append((fields, b"\x00\x08", b"\xa5", 3))
    for arguments in [b"\x02\x08", b"\xff\x08", b"\x00\x00", b"\x00\x09", b"\x01\xff"]:
        cases.append(({}, arguments, b"\xa5", 3))
    for fields in [{8: 0}, {8: 2}, {10: 0}, {10: 65}]:
        cases.append((fields, b"\x00\x08", b"\xa5", 4))
    cases += [
        ({}, b"\x00\x08", b"", 4),
        ({8: 65}, b"\x00\x08", bytes(range(64)), 4),
        ({}, b"\x00\x00", bytes(range(64)), 3),
    ]
    for ident, (changes, arguments, payload, status) in enumerate(cases, 200):
        actual = await reject_request(
            dut, controller, tap, ident, changes, arguments, payload
        )
        assert actual == status, (ident, actual, status)
        # A real subsequent DR exchange must work with preserved IR, not merely
        # an empty host channel. No reset or firmware reload between requests.
        await scan(dut, controller, tap, ident + 100, False, b"\x5a\x01", 9)
    await scan(dut, controller, tap, 400, True, b"\x1f", 5)
    assert (
        await reject_request(dut, controller, tap, 401, {}, b"\x00\x00", b"\xa5") == 3
    )
    await scan(dut, controller, tap, 402, False, b"\x00", 1)
