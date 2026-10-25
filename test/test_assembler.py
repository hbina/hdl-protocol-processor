from pathlib import Path

import pytest

from tools.assembler import AssemblyError, PROGRAM_WORDS, assemble


ROOT = Path(__file__).resolve().parents[1]


def test_all_example_firmware_fits_program_memory() -> None:
    for source in sorted((ROOT / "firmware").glob("*.asm")):
        words = assemble(source.read_text())
        assert words
        assert len(words) <= PROGRAM_WORDS
        assert all(0 <= word <= 0xFFFF for word in words)


def test_labels_and_core_encodings() -> None:
    assert assemble(
        """
        LDI r2, 0xa5
    loop:
        OUTBIT r2, 7
        DJNZ r2, loop
        WAITPIN 3, 1
        HALT
        """
    ) == [0x12A5, 0xE207, 0xA201, 0xF503, 0xF000]


@pytest.mark.parametrize(
    "source",
    [
        "LDI r4, 0",
        "OUTBIT r0, 8",
        "WAIT 256",
        "missing_instruction r0",
        "duplicate: NOP\nduplicate: HALT",
    ],
)
def test_invalid_programs_are_rejected(source: str) -> None:
    with pytest.raises(AssemblyError):
        assemble(source)


@pytest.mark.parametrize(
    "mnemonic,base",
    [
        ("LOAD", 0x2400),
        ("STORE", 0x3400),
        ("PREAD", 0x2800),
        ("PWRITE", 0x3800),
        ("CMPLT", 0x1800),
    ],
)
def test_runtime_register_encodings(mnemonic, base):
    assert assemble(f"{mnemonic} r2, r3") == [base | 0x203]


def test_extended_branches_and_comparisons():
    assert assemble(
        "JMP 63\nJMP 64\nJMP 127\nJFAIL 63\nJFAIL 64\nJZ r2, 64\nDJNZ r3, 127\nCMPI r1, 255\nCMPLTI r2, 65"
    ) == [0x803F, 0x8440, 0x847F, 0x883F, 0x8C40, 0x9640, 0xA77F, 0x15FF, 0x1E41]


@pytest.mark.parametrize("source", ["JMP 128", "JFAIL -1", "NOP\n" * 129])
def test_program_boundaries(source):
    with pytest.raises(AssemblyError):
        assemble(source)
