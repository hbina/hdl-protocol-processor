"""Binary compatibility and address/register boundaries of isolated ISA study."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from generic_frontier import assemble as frontier_assemble

from tools.assembler import assemble


def test_legacy_images_keep_identical_instruction_words():
    for path in (ROOT / "firmware").glob("*.asm"):
        assert frontier_assemble(path.read_text()) == assemble(path.read_text()), path


def test_wide_instruction_binary_contract():
    # Fixed words, independent of the assembler's source-rewrite machinery.
    assert frontier_assemble("""
        LDI R7, 0xa5
        MOV r0, r7
        LOAD r6, r5
        PREAD r7, r6
        STORE r5, r7
        DJNZ r7, 512
        JZ r4, 1023
        JMP 1023
        JFAIL 512
    """) == [
        0x113A5,
        0x2B003,
        0x32601,
        0x32B02,
        0x33503,
        0x3A700,
        0x39CFF,
        0x286FF,
        0x28C00,
    ]


def test_branch_banks_and_illegal_operands():
    for address in [63, 64, 127, 128, 255, 256, 511, 512, 767, 768, 1023]:
        for operation in ["JMP", "JFAIL", "JZ r7,", "DJNZ r7,"]:
            (word,) = frontier_assemble(f"{operation} {address}")
            conditional = word >> 12 & 15 in {9, 10}
            if word & 0x400:
                bank8 = (word >> (11 if conditional else 9)) & 1
                decoded = ((word >> 17) & 1) * 512 + bank8 * 256 + (word & 255)
            else:
                decoded = word & 63
            assert decoded == address
    for source in ["LDI r8, 0", "JMP 1024", "JZ r4, -1", "LDI r7, 256", "r7: HALT"]:
        with pytest.raises(ValueError):
            frontier_assemble(source)
