"""Generated UART image and software-clock accounting across borrow boundaries."""

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_uart_runtime import charge, generate
from generic_frontier import assemble, base_assembler

from tools.assembler import assemble as production_assemble


def test_uart_runtime_source_and_capacity():
    source = (
        ROOT / "study/protocol_exploration/uart_runtime_candidate.asm"
    ).read_text()
    assert source == generate() and len(assemble(source)) == 251
    with pytest.raises(ValueError, match="program contains 251 words; maximum is 128"):
        production_assemble(source)


def execute_debit(code, value, prefix, expired_label):
    # Independent scalar ISA execution for the generated debit block; no use
    # of its branch-balancing metadata to determine elapsed clocks.
    instructions, labels = base_assembler()._parse_lines(code)
    registers = [0] * 8
    registers[1], registers[3] = 0x51, 0xA5
    registers[4:7] = [value >> 16, value >> 8 & 255, value & 255]
    pc, elapsed, condition = 0, prefix, False
    while pc != labels[expired_label]:
        _line, op, args = instructions[pc]
        pc += 1
        elapsed += int(args[0], 0) + 1 if op == "WAIT" else 1
        reg = int(args[0][1:]) if args and args[0].startswith("r") else None
        if op == "LDI":
            registers[reg] = int(args[1], 0)
        elif op == "ADDI":
            registers[reg] = (registers[reg] + int(args[1], 0)) & 255
        elif op == "CMPLTI":
            condition = registers[reg] < int(args[1], 0)
        elif op == "MOV":
            registers[reg] = registers[int(args[1][1:])]
        elif op == "OR":
            registers[reg] |= registers[int(args[1][1:])]
        elif op in {"JMP", "JFAIL", "JZ"}:
            taken = op == "JMP" or (
                not condition if op == "JFAIL" else registers[reg] == 0
            )
            if taken:
                target = args[-1]
                if target == "search":
                    break
                pc = labels[target]
        else:
            assert op in {"WAIT", "NOP"}, op
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
