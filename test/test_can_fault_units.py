"""Persistent CAN error-state firmware freshness and production capacity."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_can_fault import generate
from build_can_fault_inline import generate as inline_source
from generic_call_frontier import assemble as call_assemble
from generic_frontier import assemble as frontier_assemble

from tools.assembler import assemble


def test_can_fault_generation_and_capacity():
    source = (ROOT / "study/protocol_exploration/can_fault_candidate.asm").read_text()
    assert source == generate().to_asm()
    assert len(call_assemble(source)) == 1016
    with pytest.raises(ValueError, match="program contains 1016 words; maximum is 128"):
        assemble(source)
    inlined = (
        ROOT / "study/protocol_exploration/can_fault_inline_candidate.asm"
    ).read_text()
    assert inlined == inline_source().to_asm()
    with pytest.raises(
        ValueError, match="program contains 1092 words; maximum is 1024"
    ):
        frontier_assemble(inlined)
