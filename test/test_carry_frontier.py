"""Encoding, compatibility and reproducible USB carry-study firmware."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_usb_dense import generate as dense_source
from build_usb_out import generate as out_source
from generic_carry_frontier import assemble

from tools.assembler import assemble as production_assemble


def test_carry_encoding_and_legacy_compatibility():
    assert assemble("SHRC r3\nRRC r6\nJNC 512") == [0x2D700, 0x3DE00, 0x28D00]
    for path in (ROOT / "firmware").glob("*.asm"):
        assert assemble(path.read_text()) == production_assemble(path.read_text()), path


def test_carry_operand_boundaries():
    for source in ["SHRC r8", "RRC", "RRC r0, r1", "JNC -1", "JNC 1024"]:
        with pytest.raises(ValueError):
            assemble(source)
    for address in [0, 63, 64, 255, 256, 511, 512, 767, 768, 1023]:
        assert assemble(f"JNC {address}")[0] == assemble(f"JFAIL {address}")[0] | 0x100


def test_generated_carry_firmware_and_production_capacity():
    directory = ROOT / "study/protocol_exploration"
    for name, generate, length in [
        ("usb_dense", dense_source, 310),
        ("usb_out", out_source, 403),
    ]:
        source = (directory / f"{name}_candidate.asm").read_text()
        assert source == generate().to_asm()
        assert len(assemble(source)) == length
        with pytest.raises(ValueError):
            production_assemble(source)
