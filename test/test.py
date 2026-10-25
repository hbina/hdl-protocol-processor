# SPDX-FileCopyrightText: © 2026 Protocol Emulator contributors
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
import sys

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge, Timer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.assembler import PROGRAM_WORDS, assemble  # noqa: E402
from tools.isa import (  # noqa: E402
    CMPI,
    CMPLT,
    CMPLTI,
    DJNZ,
    HALT,
    JFAIL,
    JMP,
    JZ,
    LDI,
    LOAD,
    STORE,
    Label,
    r0,
    r1,
    r2,
    r3,
)
from tools.program import Image, Program  # noqa: E402
from tools.runtime import Request, RuntimeController, TransportError  # noqa: E402
import random


def firmware(name: str) -> list[int]:
    words = assemble((ROOT / "firmware" / name).read_text())
    assert len(words) <= PROGRAM_WORDS
    return words


async def reset(dut, pin_input: int = 0) -> None:
    await Timer(1, unit="ps")
    dut.ena.value = 1
    dut.ui_in.value = 0x80  # Hold execution while uninitialized program memory exists.
    dut.uio_in.value = pin_input
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def load_program(dut, program: list[int] | Image | Program) -> None:
    """Load words through ui[7:0], using three six-bit chunks per word."""

    if isinstance(program, Program):
        program = program.link()
    if isinstance(program, Image):
        dut._log.debug("loading program:\n%s", program.disassemble())
        words = program.words
    else:
        words = program
    dut.ui_in.value = 0x80
    await RisingEdge(dut.clk)

    for word in words:
        for shift in (0, 6, 12):
            chunk = (word >> shift) & 0x3F
            dut.ui_in.value = 0x80 | chunk
            await RisingEdge(dut.clk)
            dut.ui_in.value = 0xC0 | chunk
            await RisingEdge(dut.clk)
            dut.ui_in.value = 0x80 | chunk
            await RisingEdge(dut.clk)

    dut.ui_in.value = 0
    await RisingEdge(dut.clk)


async def sample_pins(dut, cycles: int) -> list[tuple[int, int]]:
    samples: list[tuple[int, int]] = []
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        await ReadOnly()
        samples.append((int(dut.uio_out.value), int(dut.uio_oe.value)))
    return samples


@cocotb.test()
async def test_protocol_firmware(dut):
    """Load and execute UART, SPI, and I2C firmware on the same core."""

    clock = Clock(dut.clk, 20, unit="ns")
    cocotb.start_soon(clock.start())

    # UART: decode the generated 8N1 waveform and verify 50 clocks per bit.
    await reset(dut)
    await load_program(dut, firmware("uart_tx.asm"))
    uart_samples = await sample_pins(dut, 560)

    start = next(
        index
        for index in range(1, len(uart_samples))
        if uart_samples[index - 1][0] & 1 and not uart_samples[index][0] & 1
    )
    assert all(oe & 0x01 for _, oe in uart_samples[start:])
    frame = [0] + [(0xA5 >> bit) & 1 for bit in range(8)] + [1]
    decoded = [uart_samples[start + 25 + 50 * bit][0] & 1 for bit in range(10)]
    assert decoded == frame

    # SPI mode 0: a permanently high MISO must produce 0xff in receive r1.
    await reset(dut, pin_input=0x08)
    await load_program(dut, firmware("spi_mode0.asm"))
    spi_samples = await sample_pins(dut, 260)

    rising_mosi: list[int] = []
    previous_clock = 0
    outputs_enabled = False
    for pin_out, pin_oe in spi_samples:
        clock_value = (pin_out >> 1) & 1
        outputs_enabled |= pin_oe & 0x06 == 0x06
        if outputs_enabled:
            assert pin_oe & 0x06 == 0x06
        if not previous_clock and clock_value:
            rising_mosi.append((pin_out >> 2) & 1)
        previous_clock = clock_value

    assert rising_mosi == [1, 0, 1, 0, 0, 1, 0, 1]
    controller = PinController(dut)
    assert await controller.read(0x10C) == 0xFF

    # Pull-ups make SCL/SDA high when released. Holding SDA high models NACK.
    await reset(dut, pin_input=0x30)
    await load_program(dut, firmware("i2c_write.asm"))
    i2c_samples = await sample_pins(dut, 360)
    oe_values = [oe for _, oe in i2c_samples]

    start_drive = oe_values.index(0x20)
    clock_drive = oe_values.index(0x30, start_drive)
    assert start_drive < clock_drive
    assert oe_values[-1] == 0x10

    controller = PinController(dut)
    assert await controller.read(0x10E) & 1 == 1


class PinController(RuntimeController):
    def __init__(self, dut, seed=123):
        self.dut = dut
        self.toggle = 0
        self.random = random.Random(seed)
        super().__init__(self.token)

    async def token(self, token):
        await Timer(self.random.randint(3, 31), unit="ns")
        self.toggle ^= 1
        self.dut.ui_in.value = (self.toggle << 6) | token
        for _ in range(100):
            await Timer(20, unit="ns")
            response = int(self.dut.uo_out.value)
            if response >> 7 == self.toggle:
                # Check stability with no new request, even off clock edges.
                await Timer(23, unit="ns")
                assert int(self.dut.uo_out.value) == response
                if response & 64:
                    raise TransportError(response & 63)
                return response & 63
        raise TimeoutError("runtime token acknowledgement timed out")


@cocotb.test()
async def test_runtime_requests(dut):
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut)
    await load_program(dut, firmware("runtime.asm"))
    controller = PinController(dut)
    assert await controller.capabilities() == dict(
        version=1,
        program_words=128,
        payload_depth=64,
        record_bytes=16,
        parameter_bytes=128,
    )
    rng = random.Random(90210)
    for index, length in enumerate([0, 1, 63, 64, 64, 1, 0, 23]):
        payload = bytes(rng.randrange(256) for _ in range(length))
        operation = 1 + index % 2
        request = Request(
            0x8000 + index,
            operation,
            17 if operation == 2 else 0,
            operation - 1,
            length,
            length,
        )
        arguments = bytes([0xA5]) if operation == 2 else b""
        await controller.submit(request, payload, arguments)
        # Params and new payload cannot be altered after submission.
        for address in [17, 0x110, 0x100, 0x121]:
            try:
                await controller.write(address, 1 if address == 0x100 else 0)
            except TransportError as exc:
                assert exc.code == 8
            else:
                assert False, "pending request accepted a forbidden write"
        output, event = await controller.complete(request)
        assert event.status == 0, event
        expected = payload if operation == 1 else bytes(x ^ 0xA5 for x in payload)
        assert output == [(x, 0) for x in expected]
        assert await controller.read(0x101) == 0
    # Recover from bad operations, flags, argument layouts, and output limits.
    for index, request in enumerate(
        [
            Request(10, 99, input_count=3, output_limit=3),
            Request(11, 1, input_count=3, output_limit=3, flags=1),
            Request(12, 2, input_count=3, output_limit=3),
            Request(13, 1, input_count=3, output_limit=2),
        ]
    ):
        await controller.submit(request, b"abc")
        output, event = await controller.complete(request)
        assert output == []
        assert event.status == [2, 1, 3, 4][index], event
    request = Request(14, 1, input_count=3, output_limit=3)
    await controller.submit(request, b"end")
    output, event = await controller.complete(request)
    assert event.status == 0 and output == [(x, 0) for x in b"end"]


@cocotb.test()
async def test_runtime_transport_and_boundaries(dut):
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut)
    await load_program(dut, assemble("HALT"))
    controller = PinController(dut, 4)

    async def denied(address, value, code):
        try:
            if value is None:
                await controller.read(address)
            else:
                await controller.write(address, value)
        except TransportError as exc:
            assert exc.code == code, (address, exc.code)
        else:
            assert False, (address, "unexpected success")

    await denied(0x80, 1, 4)
    await denied(0x80, None, 4)
    await denied(0x105, 1, 4)
    await denied(0x200, None, 3)
    await denied(0x133, None, 5)
    await denied(0x121, 0, 7)
    for value in range(16):
        await controller.write(0x120, value)
        assert await controller.read(0x104) == 0
    await denied(0x120, 0, 6)
    await controller.write(0x100, 1)
    for value in range(64):
        await controller.write(0x110, value)
    assert await controller.read(0x102) == 64
    await denied(0x110, 99, 6)
    await controller.write(0x100, 1)
    assert await controller.read(0x102) == 0
    # Invalid opcode, high address padding, and high data padding recover parser.
    for tokens in [[2], [0, 0, 0, 16], [1, 0, 0, 0, 12, 4]]:
        try:
            for token in tokens:
                await controller.token(token)
        except TransportError as exc:
            assert exc.code in [1, 2]
        else:
            assert False, "malformed token sequence accepted"
        assert await controller.read(0x106) == 1
    for value in [0, 63, 64, 255]:
        await controller.write(127, value)
        assert await controller.read(127) == value
    # Reset while a bus packet and record are only partially assembled.
    await controller.write(0x120, 123)
    await controller.token(1)
    await controller.token(5)
    await reset(dut)
    await load_program(dut, assemble("HALT"))
    controller = PinController(dut)
    assert await controller.read(0x101) == 0
    await denied(0x121, 0, 7)


@cocotb.test()
async def test_runtime_isa_and_gpio_timing(dut):
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut)
    fail, expected, far = Label("fail"), Label("expected"), Label("far")
    program = Program(
        [LDI(r0, 0x5A), LDI(r1, 128), STORE(r0, r1), LDI(r0, 0), LOAD(r2, r1)]
        + [CMPI(r2, 0x5A), JFAIL(fail), CMPLTI(r2, 100), JFAIL(fail)]
        + [CMPLT(r0, r2), JFAIL(fail), LDI(r1, 0), STORE(r2, r1), JFAIL(expected)]
        + [fail, LDI(r3, 0xEE), HALT()]
        + [expected, JMP(far)]
    )
    program.pad_to(127).mark(far)  # the last program word
    program += HALT()
    await load_program(dut, program.link())
    await ClockCycles(dut.clk, 100)
    controller = PinController(dut)
    assert await controller.read(0x10D) == 0x5A
    assert await controller.read(0x10E) == 0
    # Loader crosses 64 words; both long conditional/decrement branches execute.
    far, conditional, loop = Label("far"), Label("conditional"), Label("loop")
    program = Program([JMP(far)]).pad_to(64).mark(far)
    program += [LDI(r0, 0), JZ(r0, conditional), LDI(r3, 1)]
    program += [conditional, LDI(r0, 2), loop, DJNZ(r0, loop), HALT()]
    await reset(dut)
    await load_program(dut, program.link())
    await ClockCycles(dut.clk, 20)
    controller = PinController(dut)
    assert await controller.read(0x10B) == 0
    assert await controller.read(0x10E) == 0
    # Memory and peripheral operations remain exactly two clocks even while
    # the host competes for the shared access path (each high pulse is 3 clocks).
    await reset(dut)
    await load_program(
        dut,
        assemble("""
        LDI r0, 42
        LDI r1, 128
        STORE r0, r1
        SETOE 1
        SETO 1
        LOAD r2, r1
        SETO 0
        LDI r1, 6
        SETO 1
        PREAD r0, r1
        SETO 0
        HALT
    """),
    )
    controller = PinController(dut)
    traffic = cocotb.start_soon(controller.capabilities())
    samples = await sample_pins(dut, 30)
    await traffic
    runs = []
    length = 0
    for value, _ in samples:
        if value & 1:
            length += 1
        elif length:
            runs.append(length)
            length = 0
    assert runs == [3, 3]
    # Pause after issue: the access drains once, future issue remains stopped.
    # GPIO marks the instruction immediately before the input pop; no internal
    # hierarchy is used, so this scenario also runs on the mapped netlist.
    await reset(dut)
    await load_program(
        dut,
        assemble("""
        LDI r3, 0x22
    wait_request:
        PREAD r0, r3
        JFAIL wait_request
        LDI r1, 15
    rest:
        PREAD r0, r3
        DJNZ r1, rest
        LDI r3, 0x11
        SETOE 1
        SETO 1
        PREAD r0, r3
        SETO 0
        PREAD r1, r3
        HALT
    """),
    )
    controller = PinController(dut)
    for value in [0x12, 0x34]:
        await controller.write(0x110, value)
    for value in Request(999, 1, input_count=2, output_limit=2).encode():
        await controller.write(0x120, value)
    await controller.write(0x121, 0)
    for _ in range(1000):
        if int(dut.uio_out.value) & 1:
            break
        await Timer(5, unit="ns")
    else:
        assert False, "no input-pop marker"
    await RisingEdge(dut.clk)  # first access cycle
    await Timer(1, unit="ns")
    dut.ena.value = 0
    await ClockCycles(dut.clk, 3)
    assert await controller.read(0x102) == 1
    assert await controller.read(0x10B) == 0x12
    assert int(dut.uio_out.value) & 1  # following SETO is still paused
    dut.ena.value = 1
    await ClockCycles(dut.clk, 10)
    assert await controller.read(0x102) == 0
    assert await controller.read(0x10C) == 0x34
    # Configuration between issue and commit must abort a scratch write.
    # Scratch survives configuration, so reloaded firmware can expose whether
    # the canceled access accidentally reached memory.
    await reset(dut)
    await load_program(
        dut,
        assemble("""
        LDI r1, 128
        LDI r0, 0xaa
        STORE r0, r1
        LDI r3, 0x22
    wait_request:
        PREAD r0, r3
        JFAIL wait_request
        LDI r0, 0xbb
        SETOE 1
        SETO 1
        STORE r0, r1
        HALT
    """),
    )
    controller = PinController(dut)
    for value in Request(1000, 1).encode():
        await controller.write(0x120, value)
    await controller.write(0x121, 0)
    for _ in range(1000):
        if int(dut.uio_out.value) & 1:
            break
        await Timer(5, unit="ns")
    else:
        assert False, "no scratch-write marker"
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")  # write is issued, but has not committed
    await load_program(dut, assemble("LDI r1, 128\nLOAD r0, r1\nHALT"))
    controller = PinController(dut)
    assert await controller.read(0x10B) == 0xAA
    assert await controller.read(0x101) == 0
    # Asynchronous host traffic while legacy UART runs must preserve every edge.
    await reset(dut)
    await load_program(dut, firmware("uart_tx.asm"))
    controller = PinController(dut)
    traffic = cocotb.start_soon(controller.capabilities())
    samples = await sample_pins(dut, 560)
    await traffic
    start = next(
        i
        for i in range(1, len(samples))
        if samples[i - 1][0] & 1 and not samples[i][0] & 1
    )
    frame = [0] + [(0xA5 >> bit) & 1 for bit in range(8)] + [1]
    assert [samples[start + 25 + 50 * bit][0] & 1 for bit in range(10)] == frame


@cocotb.test()
async def test_runtime_malformed_records_and_retirement(dut):
    from tools.runtime import Completion

    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut)
    await load_program(dut, firmware("runtime.asm"))
    controller = PinController(dut, 100)

    async def raw_submit(record, payload):
        assert await controller.read(0x101) == 0
        for value in payload:
            await controller.write(0x110, value)
        for value in record:
            await controller.write(0x120, value)
        await controller.write(0x121, 0)
        for _ in range(1000):
            if await controller.read(0x105):
                return
        assert False, "no terminal event"

    cases = [
        (Request(101, 1, input_count=2, output_limit=3).encode(), b"abc", 4),
        (Request(102, 1, output_limit=65).encode(), b"", 4),
        (Request(103, 2, arguments_address=128, arguments_length=1).encode(), b"", 3),
        (Request(104, 2, arguments_address=256, arguments_length=1).encode(), b"", 1),
        (Request(105, 1).encode()[:-1] + b"\x01", b"", 1),
        (Request(106, 1, input_count=65, output_limit=64).encode(), bytes(64), 4),
    ]
    for record, payload, status in cases:
        await raw_submit(record, payload)
        assert await controller.read(0x103) == 0
        event = Completion.decode(
            bytes([await controller.read(0x142) for _ in range(16)])
        )
        assert event.status == status
        assert event.input_consumed == len(payload) and event.output_produced == 0
        assert await controller.read(0x101) == 0

    await raw_submit(Request(200, 1, input_count=3, output_limit=3).encode(), b"abc")
    prefix = bytes([await controller.read(0x142) for _ in range(15)])
    try:
        await controller.read(0x142)
    except TransportError as exc:
        assert exc.code == 8
    else:
        assert False, "terminal event retired before draining output"
    assert await controller.read(0x101) & 1
    for value in b"abc":
        assert await controller.read(0x133) == value
        assert await controller.read(0x134) == 0
        await controller.write(0x135, 0)
    event = Completion.decode(prefix + bytes([await controller.read(0x142)]))
    assert event.request_id == 200 and event.status == 0
    assert await controller.read(0x101) == 0

    # Abort a committed request by configuration reset. Pending ownership and
    # all record/payload state must be released, and the loader restarts at zero.
    await load_program(dut, assemble("HALT"))
    controller = PinController(dut)
    for value in Request(201, 1).encode():
        await controller.write(0x120, value)
    await controller.write(0x121, 0)
    assert await controller.read(0x101) & 1
    await load_program(dut, firmware("runtime.asm"))
    controller = PinController(dut)
    request = Request(202, 2, 127, 1, 3, 3)
    await controller.submit(request, b"end", b"\x91")
    output, event = await controller.complete(request)
    assert event.status == 0 and output == [(x ^ 0x91, 0) for x in b"end"]
