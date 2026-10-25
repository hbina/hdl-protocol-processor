"""Generated UART image and software-clock accounting across borrow boundaries."""

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_uart_runtime import charge, generate
from generic_frontier import assemble

from tools.assembler import assemble as production_assemble
from tools.isa import (
    FRONTIER,
    CondJump,
    CondJumpOp,
    Imm,
    ImmOp,
    Jump,
    JumpOp,
    Label,
    Nop,
    RegImm,
    RegImmOp,
    RegReg,
    RegRegOp,
)


def test_uart_runtime_source_and_capacity():
    source = (
        ROOT / "study/protocol_exploration/uart_runtime_candidate.asm"
    ).read_text()
    assert source == generate().to_asm() and len(assemble(source)) == 251
    with pytest.raises(ValueError, match="program contains 251 words; maximum is 128"):
        production_assemble(source)


def execute_debit(code, value, prefix, expired_label):
    # Independent scalar ISA execution for the generated debit block; no use
    # of its branch-balancing metadata to determine elapsed clocks. The block
    # exits to "search" and "fail", so those labels are placed after it.
    program = code + [Label("search"), Label("fail")]
    instructions = program.instructions()
    labels = program.link(FRONTIER).symbols
    registers = [0] * 8
    registers[1], registers[3] = 0x51, 0xA5
    registers[4:7] = [value >> 16, value >> 8 & 255, value & 255]
    pc, elapsed, condition = 0, prefix, False
    while pc != labels[expired_label]:
        insn = instructions[pc]
        pc += 1
        elapsed += 1
        target = None
        match insn:
            case Imm(op=ImmOp.WAIT, imm=imm):
                elapsed += imm
            case Nop():
                pass
            case RegImm(op=RegImmOp.LDI, rd=rd, imm=imm):
                registers[rd.index] = imm
            case RegImm(op=RegImmOp.ADDI, rd=rd, imm=imm):
                registers[rd.index] = (registers[rd.index] + imm) & 255
            case RegImm(op=RegImmOp.CMPLTI, rd=rd, imm=imm):
                condition = registers[rd.index] < imm
            case RegReg(op=RegRegOp.MOV, rd=rd, rs=rs):
                registers[rd.index] = registers[rs.index]
            case RegReg(op=RegRegOp.OR, rd=rd, rs=rs):
                registers[rd.index] |= registers[rs.index]
            case Jump(op=JumpOp.JMP, target=t):
                target = t
            case Jump(op=JumpOp.JFAIL, target=t) if not condition:
                target = t
            case CondJump(op=CondJumpOp.JZ, rd=rd, target=t) if (
                registers[rd.index] == 0
            ):
                target = t
            case Jump(op=JumpOp.JFAIL) | CondJump(op=CondJumpOp.JZ):
                pass
            case _:
                raise AssertionError(f"unexpected instruction {insn}")
        if target is not None:
            assert isinstance(target, Label) and target.name
            if target.name == "search":
                break
            pc = labels[target.name]
    assert registers[1] == 0x51 and registers[3] == 0xA5
    return (
        elapsed,
        registers[7] != 0,
        (registers[4] << 16) | (registers[5] << 8) | registers[6],
    )


def test_deadline_debits_use_exact_clocks_and_saturate_expiration():
    rng = random.Random(0x434C4F434B)
    values = [
        0,
        1,
        31,
        32,
        33,
        255,
        256,
        257,
        65535,
        65536,
        65537,
        255 * 65536,
        *[rng.randrange(1 << 24) for _ in range(500)],
    ]
    for amount, prefix, period in [(32, 5, 32), (256, 217, 256)]:
        code = charge(amount, prefix, period, "expired")
        for value in values:
            elapsed, expired, remaining = execute_debit(code, value, prefix, "expired")
            assert elapsed == period
            assert expired == (value <= amount), (value, amount)
            if not expired:
                assert remaining == value - amount
