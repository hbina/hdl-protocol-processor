"""Generic ISA diagnostics and combined CAN request alternation on study model."""

import os
from pathlib import Path

import cocotb
from can_peer import frame
from can_tx_peer import Receiver
from cocotb.clock import Clock
from cocotb.triggers import Timer
from generic_frontier import assemble

from test import PinController, load_program, reset
from tools.isa import (
    ADDI,
    CMPI,
    CMPLT,
    DJNZ,
    FRONTIER,
    HALT,
    JFAIL,
    JMP,
    JZ,
    LDI,
    LOAD,
    MOV,
    STORE,
    XOR,
    r0,
    r1,
    r2,
    r3,
    r4,
    r5,
    r6,
    r7,
)
from tools.program import place
from tools.runtime import Request


@cocotb.test(timeout_time=10, timeout_unit="ms")
async def test_frontier_registers_loader_banks(dut):
    assert os.environ.get("GENERIC_FRONTIER_EXPERIMENT") == "1"
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=0xFF)
    image = place(
        {
            0: MOV(r0, r7),
            1: CMPI(r0, 0),
            2: JFAIL(900),
            3: LDI(r4, 128),
            4: LDI(r5, 0x5A),
            5: STORE(r5, r4),
            6: LOAD(r6, r4),
            7: CMPI(r6, 0x5A),
            8: JFAIL(900),
            9: MOV(r7, r6),
            10: XOR(r7, r5),
            11: JZ(r7, 512),
            12: JMP(900),
            512: LDI(r7, 2),
            513: DJNZ(r7, 513),
            514: CMPI(r7, 0),
            515: JFAIL(900),
            516: JMP(256),
            256: LDI(r4, 0xA5),
            257: LDI(r5, 0x22),
            258: MOV(r0, r4),
            259: JMP(768),
            768: MOV(r4, r5),
            769: ADDI(r4, 1),
            770: MOV(r1, r4),
            771: CMPLT(r7, r4),
            772: JFAIL(900),
            773: CMPI(r4, 0),
            774: JFAIL(1020),
            900: LDI(r0, 0xEE),
            901: HALT(),
            1020: MOV(r2, r6),
            1021: LDI(r3, 0x77),
            1022: JMP(1023),
            1023: HALT(),
        },
        1024,
    )
    await load_program(dut, image.link(FRONTIER).words)
    await Timer(3, unit="us")
    dut.ena.value = 0
    controller = PinController(dut)
    assert [await controller.read(address) for address in range(0x10B, 0x10F)] == [
        0xA5,
        0x23,
        0x5A,
        0x77,
    ]
    # Reload must reset all8 registers; test high-destination peripheral reads
    # and high-register GPIO operations, which have separate RTL commit paths.
    await load_program(
        dut,
        assemble("""
        MOV r0, r7
        LDI r4, 6
        PREAD r5, r4
        MOV r1, r5
        LDI r4, 2
        OE r4
        LDI r5, 0xa5
        OUT r5
        IN r6
        LDI r7, 0
        INBIT r7, 3
        SHL r7
        OR r7, r4
        CMPLTI r7, 2
        JFAIL ready
        LDI r0, 0xee
    ready:
        MOV r2, r6
        MOV r3, r7
        HALT
    """),
    )
    dut.ena.value = 1
    await Timer(2, unit="us")
    dut.ena.value = 0
    assert [await controller.read(address) for address in range(0x10B, 0x10F)] == [
        0,
        1,
        0xFF,
        2,
    ]
    assert int(dut.uio_out.value) == 0xA5 and int(dut.uio_oe.value) == 2


async def setup(dut):
    assert os.environ.get("GENERIC_FRONTIER_EXPERIMENT") == "1"
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    await reset(dut, pin_input=2)
    bus = Receiver(dut)
    cocotb.start_soon(bus.resolve())
    source = Path(__file__).with_name("can_frontier_candidate.asm").read_text()
    await load_program(dut, assemble(source))
    return PinController(dut, 0x102418), bus


async def tx(controller, bus, ident, identifier, data, *, status=0, **kwargs):
    request = Request(ident, 2, arguments_length=3, input_count=len(data))
    listener = cocotb.start_soon(bus.listen(identifier, data, **kwargs))
    await controller.submit(
        request, data, bytes([identifier >> 8, identifier & 255, len(data)])
    )
    output, event = await controller.complete(request, poll_limit=30000)
    await listener
    assert output == [] and event.status == status, event
    assert event.input_consumed == len(data) and event.output_produced == 0
    assert await controller.read(0x101) == 0


async def rx(controller, bus, ident, identifier, data, *, corrupt=False):
    request = Request(ident, 1, output_limit=11)
    await controller.submit(request, b"")
    await Timer(110, unit="us")
    wire, ack, _ = frame(identifier, data, crc_error=corrupt)
    sender = cocotb.start_soon(bus.send(wire, ack, acknowledge=not corrupt))
    output, event = await controller.complete(request, poll_limit=30000)
    await sender
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
    assert await controller.read(0x101) == 0


@cocotb.test(timeout_time=40, timeout_unit="ms")
async def test_frontier_can_alternating_tx_rx(dut):
    controller, bus = await setup(dut)
    for index, data in enumerate(
        [b"", b"\x00", b"\xff" * 8, b"\x55\xaa\x12\x34\x56\x78\x01\x80"]
    ):
        await tx(controller, bus, index * 2, 0x123 + index, data)
        await rx(controller, bus, index * 2 + 1, 0x456 + index, data[::-1])


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def test_frontier_can_cross_mode_recovery(dut):
    controller, bus = await setup(dut)
    await tx(controller, bus, 20, 0x321, b"\xff" * 8, ack=False, status=24)
    await rx(controller, bus, 21, 0, bytes(8))
    await rx(controller, bus, 22, 0x123, b"\xa5", corrupt=True)
    await tx(controller, bus, 23, 0x456, b"\x5a")
    await tx(controller, bus, 24, 0x7FF, b"\x55", winner=0x3FF, status=22)
    await rx(controller, bus, 25, 0x321, b"\xaa")
