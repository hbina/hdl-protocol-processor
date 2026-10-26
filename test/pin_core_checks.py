"""Core-level architectural checks, including every instruction word."""

import random
import cocotb
from cocotb.triggers import Timer
from tools.assembler import assemble
from tools.isa import IsaConfig, IsaError, decode


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


async def execute(dut, source, cfg, limit=200):
    await reset(dut)
    words = assemble(source, cfg)
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
        """
        LDI r0, 0
        LDI r1, 0
    write:
        STORE r0, r1
        ADDI r0, 1
        ADDI r1, 1
        JZ r1, read_start
        JMP write
    read_start:
        LDI r1, 0
    read:
        LOAD r2, r1
        CMPLT r2, r1
        JFAIL check_equal
        HALT
    check_equal:
        MOV r3, r2
        XOR r3, r1
        JZ r3, next
        HALT
    next:
        ADDI r1, 1
        JZ r1, done
        JMP read
    done:
        HALT
    """,
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
        f"""
        LDI r0, {p}
        INBIT r0, r0
        LDI r1, {no - 1}
        OUTBIT r0, r1
        OEBIT r0, r1
        OEBITN r0, {no - 1}
        IN r2, {(ni - 1) // 8}
        LDI r3, 255
        OUT r3, {(no - 1) // 8}
        OE r3, {(no - 1) // 8}
        WAITPIN {ni - 1}, 1
        LDI r1, {ni - 1}
        WAITPIN r1, 1
        HALT
    """,
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
            f"LDI r0,{a}\nLDI r1,{b}\nXOR r0,r1\nORI r0,3\nANDI r0,127\nADDI r0,17\nROL r0\nROR r0\nHALT",
            cfg,
        )
        assert regs(dut)[0] == (((a ^ b) | 3) & 127) + 17

    # Fixed RAM latency; issued writes drain across pause, and reads alias safely.
    await reset(dut)
    for i, w in enumerate(
        assemble("LDI r0,77\nLDI r1,0\nSTORE r0,r1\nLOAD r1,r1\nHALT", cfg)
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
        for i, w in enumerate(assemble("LDI r0,88\nLDI r1,0\nSTORE r0,r1\nHALT", cfg)):
            dut.core.program_mem[i].value = w
        dut.cfg_mode.value = 0
        await tick(dut, 3)
        getattr(dut, control).value = 0 if control == "rst_n" else 1
        await tick(dut)
        assert int(dut.core.memory[0].value) == 19
        assert regs(dut) == [0] * 4 and int(dut.pin_oe.value) == 0

    # Dynamic out-of-range indices halt without a GPIO/register side effect.
    if ni < 256:
        await execute(dut, f"LDI r0,255\nLDI r1,{ni}\nINBIT r0,r1\nLDI r0,0\nHALT", cfg)
        assert regs(dut)[0] == 255 and int(dut.core.pc.value) == 2
    if no < 256:
        await execute(dut, f"LDI r0,1\nLDI r1,{no}\nOUTBIT r0,r1\nHALT", cfg)
        assert int(dut.pin_out.value) == 0 and int(dut.core.pc.value) == 2

    # WAIT timing and pin wait stall; enable pauses waits and synchronization runs.
    await reset(dut)
    dut.pin_in.value = 0
    for i, w in enumerate(assemble("WAIT 2\nWAITPIN 0,1\nHALT", cfg)):
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
    image = assemble("JMP 127\n", cfg) + [0] * 255
    image[127] = assemble("JMP 128", cfg)[0]
    image[128] = assemble("JMP 255", cfg)[0]
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
    await execute(dut, "LDI r0,255\nINBIT r0,0\nHALT", cfg)
    assert regs(dut)[0] == 0
    # OE and inverted OE change direction without changing output value.
    await execute(
        dut,
        f"LDI r0,1\nOUTBIT r0,{no - 1}\nOEBIT r0,{no - 1}\nOEBITN r0,{no - 1}\nHALT",
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
            f"LDI r0,1\nOUTBIT r0,0\nLDI r0,255\nOE r0,0\nOUT r0,{(no - 1) // 8}\nHALT",
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
            f"LDI r0,{a}\nLDI r1,{b}\nMOV r2,r0\nAND r0,r1\nOR r2,r1\nADDI r2,{n}\nSHL r0\nSHR r0\nCMPI r1,{b}\nJFAIL bad\nCMPLTI r1,255\nLDI r3,77\nHALT\nbad: LDI r3,99\nHALT",
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
