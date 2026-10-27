"""Core-level architectural checks, including every instruction word."""

import random
import cocotb
from cocotb.triggers import Timer
from tools.program import Program
from tools.isa import (
    IsaConfig,
    IsaError,
    decode,
    ADDI,
    AND,
    ANDI,
    CMPI,
    CMPLT,
    CMPLTI,
    HALT,
    IN,
    INBIT,
    JFAIL,
    JMP,
    JZ,
    LDI,
    LOAD,
    Label,
    MOV,
    OE,
    OEBIT,
    OEBITN,
    OR,
    ORI,
    OUT,
    OUTBIT,
    ROL,
    ROR,
    SHL,
    SHR,
    STORE,
    WAIT,
    WAITPIN,
    XOR,
    r0,
    r1,
    r2,
    r3,
)


async def tick(dut, count=1):
    for _ in range(count):
        dut.clk.value = 0
        await Timer(10, unit="ns")
        dut.clk.value = 1
        await Timer(10, unit="ns")


async def reset(dut):
    dut.rst_n.value = 0
    dut.cfg_mode.value = 1
    dut.cfg_write.value = 0
    dut.enable.value = 1
    await tick(dut, 2)
    dut.rst_n.value = 1
    await tick(dut, 2)


def regs(dut):
    return [int(dut.core.registers[i].value) for i in range(4)]


async def execute(dut, program: Program, cfg, limit=200):
    await reset(dut)
    words = program.link(cfg).words
    for i, word in enumerate(words):
        dut.core.program_mem[i].value = word
    dut.cfg_mode.value = 0
    for _ in range(limit):
        await tick(dut)
        if int(dut.halted.value):
            return
    raise AssertionError("program did not halt")


@cocotb.test()
async def architecture(dut):
    ni, no = len(dut.pin_in), len(dut.pin_out)
    cfg = IsaConfig(input_pins=ni, output_pins=no)
    await reset(dut)
    # The hardware validator and typed decoder must agree for EVERY word.
    # Configuration holds PC=0, and instructions never execute in this sweep.
    for word in range(65536):
        dut.core.program_mem[0].value = word
        await Timer(1, unit="ns")
        try:
            decode(word, cfg)
            expected = True
        except IsaError:
            expected = False
        assert bool(int(dut.core.valid_instruction.value)) == expected, hex(word)

    # Entire RAM, including addresses 0/255, is writable and readable.
    await execute(
        dut,
        Program(
            [
                LDI(r0, 0),
                LDI(r1, 0),
                Label("write"),
                STORE(r0, r1),
                ADDI(r0, 1),
                ADDI(r1, 1),
                JZ(r1, Label("read_start")),
                JMP(Label("write")),
                Label("read_start"),
                LDI(r1, 0),
                Label("read"),
                LOAD(r2, r1),
                CMPLT(r2, r1),
                JFAIL(Label("check_equal")),
                HALT(),
                Label("check_equal"),
                MOV(r3, r2),
                XOR(r3, r1),
                JZ(r3, Label("next")),
                HALT(),
                Label("next"),
                ADDI(r1, 1),
                JZ(r1, Label("done")),
                JMP(Label("read")),
                Label("done"),
                HALT(),
            ]
        ),
        cfg,
        6000,
    )
    assert regs(dut)[1:] == [0, 255, 0], regs(dut)
    assert all(int(dut.core.memory[i].value) == i for i in range(256))

    # Immediate and register pins, register aliasing, zero extension, OE polarity.
    dut.pin_in.value = (1 << ni) - 1
    p = min(ni, no) - 1
    await execute(
        dut,
        Program(
            [
                LDI(r0, p),
                INBIT(r0, r0),
                LDI(r1, no - 1),
                OUTBIT(r0, r1),
                OEBIT(r0, r1),
                OEBITN(r0, no - 1),
                IN(r2, (ni - 1) // 8),
                LDI(r3, 255),
                OUT(r3, (no - 1) // 8),
                OE(r3, (no - 1) // 8),
                WAITPIN(ni - 1, 1),
                LDI(r1, ni - 1),
                WAITPIN(r1, 1),
                HALT(),
            ]
        ),
        cfg,
    )
    assert regs(dut)[0] == 1
    assert regs(dut)[2] == (1 << ((ni - 1) % 8 + 1)) - 1
    expected = ((1 << ((no - 1) % 8 + 1)) - 1) << (((no - 1) // 8) * 8)
    assert int(dut.pin_out.value) == expected
    assert int(dut.pin_oe.value) == expected

    # All existing ALU operations, with operands sampled before writes.
    rng = random.Random(401)
    for _ in range(12):
        a, b = rng.randrange(256), rng.randrange(256)
        await execute(
            dut,
            Program(
                [
                    LDI(r0, a),
                    LDI(r1, b),
                    XOR(r0, r1),
                    ORI(r0, 3),
                    ANDI(r0, 127),
                    ADDI(r0, 17),
                    ROL(r0),
                    ROR(r0),
                    HALT(),
                ]
            ),
            cfg,
        )
        assert regs(dut)[0] == (((a ^ b) | 3) & 127) + 17

    # Fixed RAM latency; issued writes drain across pause, and reads alias safely.
    await reset(dut)
    for i, w in enumerate(
        Program([LDI(r0, 77), LDI(r1, 0), STORE(r0, r1), LOAD(r1, r1), HALT()])
        .link(cfg)
        .words
    ):
        dut.core.program_mem[i].value = w
    dut.cfg_mode.value = 0
    await tick(dut, 2)
    await tick(dut)
    assert int(dut.core.pc.value) == 2 and int(dut.core.memory_pending.value) == 1
    dut.enable.value = 0
    await tick(dut)
    assert int(dut.core.pc.value) == 3 and int(dut.core.memory[0].value) == 77
    await tick(dut, 3)
    assert int(dut.core.pc.value) == 3
    dut.enable.value = 1
    await tick(dut)
    assert int(dut.core.pc.value) == 3
    await tick(dut)
    assert int(dut.core.pc.value) == 4 and regs(dut)[1] == 77

    # Reset and configuration abort writes before their commit edge.
    for control in ("rst_n", "cfg_mode"):
        await reset(dut)
        dut.core.memory[0].value = 19
        for i, w in enumerate(
            Program([LDI(r0, 88), LDI(r1, 0), STORE(r0, r1), HALT()]).link(cfg).words
        ):
            dut.core.program_mem[i].value = w
        dut.cfg_mode.value = 0
        await tick(dut, 3)
        getattr(dut, control).value = 0 if control == "rst_n" else 1
        await tick(dut)
        assert int(dut.core.memory[0].value) == 19
        assert regs(dut) == [0] * 4 and int(dut.pin_oe.value) == 0

    # Dynamic out-of-range indices halt without a GPIO/register side effect.
    if ni < 256:
        await execute(
            dut,
            Program([LDI(r0, 255), LDI(r1, ni), INBIT(r0, r1), LDI(r0, 0), HALT()]),
            cfg,
        )
        assert regs(dut)[0] == 255 and int(dut.core.pc.value) == 2
    if no < 256:
        await execute(
            dut, Program([LDI(r0, 1), LDI(r1, no), OUTBIT(r0, r1), HALT()]), cfg
        )
        assert int(dut.pin_out.value) == 0 and int(dut.core.pc.value) == 2

    # WAIT timing and pin wait stall; enable pauses waits and synchronization runs.
    await reset(dut)
    dut.pin_in.value = 0
    for i, w in enumerate(Program([WAIT(2), WAITPIN(0, 1), HALT()]).link(cfg).words):
        dut.core.program_mem[i].value = w
    dut.cfg_mode.value = 0
    await tick(dut)
    assert int(dut.core.pc.value) == 1
    await tick(dut, 2)
    assert int(dut.core.pc.value) == 1
    await tick(dut, 3)
    assert int(dut.core.pc.value) == 1
    dut.enable.value = 0
    dut.pin_in.value = 1
    await tick(dut)
    assert int(dut.core.pin_sync.value) == 0
    await tick(dut)
    assert int(dut.core.pin_sync.value) == 1 and int(dut.core.pc.value) == 1
    dut.enable.value = 1
    await tick(dut)
    assert int(dut.core.pc.value) == 2
    await tick(dut)
    assert int(dut.halted.value) == 1

    # Full 256-word loader, branch boundaries, and 8-bit PC rollover.
    await reset(dut)
    image = Program([JMP(127)]).link(cfg).words + [0] * 255
    image[127] = Program([JMP(128)]).link(cfg).words[0]
    image[128] = Program([JMP(255)]).link(cfg).words[0]
    image[255] = 0
    for word in image:
        for shift in (0, 6, 12):
            dut.cfg_data.value = (word >> shift) & 63
            dut.cfg_write.value = 0
            await tick(dut)
            dut.cfg_write.value = 1
            await tick(dut)
            dut.cfg_write.value = 0
            await tick(dut)
    assert [int(dut.core.program_mem[i].value) for i in range(256)] == image
    dut.cfg_mode.value = 0
    for pc in (127, 128, 255, 0):
        await tick(dut)
        assert int(dut.core.pc.value) == pc


@cocotb.test()
async def pin_isolation_and_alu(dut):
    """Verify state changes rather than only legality of instruction words."""
    ni, no = len(dut.pin_in), len(dut.pin_out)
    cfg = IsaConfig(input_pins=ni, output_pins=no)
    dut.pin_in.value = 0
    await execute(dut, Program([LDI(r0, 255), INBIT(r0, 0), HALT()]), cfg)
    assert regs(dut)[0] == 0
    # OE and inverted OE change direction without changing output value.
    await execute(
        dut,
        Program(
            [
                LDI(r0, 1),
                OUTBIT(r0, no - 1),
                OEBIT(r0, no - 1),
                OEBITN(r0, no - 1),
                HALT(),
            ]
        ),
        cfg,
    )
    assert int(dut.pin_out.value) == 1 << (no - 1)
    assert int(dut.pin_oe.value) == 0
    await tick(dut, 4)
    assert int(dut.pin_out.value) == 1 << (no - 1), "HALT must preserve outputs"
    # Bank writes must not modify other banks or independent enable latches.
    if no > 8:
        await execute(
            dut,
            Program(
                [
                    LDI(r0, 1),
                    OUTBIT(r0, 0),
                    LDI(r0, 255),
                    OE(r0, 0),
                    OUT(r0, (no - 1) // 8),
                    HALT(),
                ]
            ),
            cfg,
        )
        high = ((1 << ((no - 1) % 8 + 1)) - 1) << (((no - 1) // 8) * 8)
        assert int(dut.pin_out.value) == high | 1
        assert int(dut.pin_oe.value) == 255
    # No hidden dependencies on old values or arithmetic overflow behavior.
    rng = random.Random(882)
    for _ in range(20):
        a, b, n = [rng.randrange(256) for _ in range(3)]
        await execute(
            dut,
            Program(
                [
                    LDI(r0, a),
                    LDI(r1, b),
                    MOV(r2, r0),
                    AND(r0, r1),
                    OR(r2, r1),
                    ADDI(r2, n),
                    SHL(r0),
                    SHR(r0),
                    CMPI(r1, b),
                    JFAIL(Label("bad")),
                    CMPLTI(r1, 255),
                    LDI(r3, 77),
                    HALT(),
                    Label("bad"),
                    LDI(r3, 99),
                    HALT(),
                ]
            ),
            cfg,
        )
        assert regs(dut) == [(a & b) & 127, b, ((a | b) + n) & 255, 77]
        assert int(dut.core.condition_flag.value) == int(b < 255)
    # An invalid word cannot perform even the otherwise-decoded STORE effect.
    await reset(dut)
    dut.core.memory[0].value = 37
    dut.core.program_mem[0].value = 0x3404  # STORE with a reserved immediate bit
    dut.cfg_mode.value = 0
    await tick(dut)
    assert int(dut.halted.value) == 1 and int(dut.core.pc.value) == 0
    assert int(dut.core.memory[0].value) == 37 and regs(dut) == [0] * 4
