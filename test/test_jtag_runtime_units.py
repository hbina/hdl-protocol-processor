"""Validated JTAG source freshness and unchanged four-register ISA boundary."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_jtag_runtime import generate
from run_jtag_runtime import candidate_words

from tools.assembler import assemble


def test_jtag_runtime_generation_and_capacity():
    source = (
        ROOT / "study/protocol_exploration/jtag_runtime_candidate.asm"
    ).read_text()
    assert source == generate()
    words = candidate_words("jtag_runtime")
    assert len(words) == 198 and all(0 <= word < 65536 for word in words)
    with pytest.raises(ValueError, match="program contains 198 words; maximum is 128"):
        assemble(source)
