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
