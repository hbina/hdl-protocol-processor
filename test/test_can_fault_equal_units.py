"""Corrected equal-polarity CAN flag firmware and production boundary."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_can_fault_equal import generate
from generic_call_frontier import assemble as call_assemble

from tools.assembler import assemble


def test_can_fault_equal_generation_and_capacity():
    source = (
        ROOT / "study/protocol_exploration/can_fault_equal_candidate.asm"
    ).read_text()
    assert source == generate().to_asm()
    assert len(call_assemble(source)) == 1020
    with pytest.raises(ValueError, match="program contains 1020 words; maximum is 128"):
        assemble(source)
