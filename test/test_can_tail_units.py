"""Preserve the bounded CAN tail draft and its actual assembly limits."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_can_tail import generate
from generic_call_frontier import assemble as model_assemble

from tools.assembler import assemble


def test_can_tail_draft_freshness_and_capacity():
    source = (ROOT / "study/protocol_exploration/can_tail_candidate.asm").read_text()
    assert source == generate()
    with pytest.raises(
        ValueError, match="program contains 1067 words; maximum is 1024"
    ):
        model_assemble(source)
    with pytest.raises(ValueError, match="program contains 1067 words; maximum is 128"):
        assemble(source)
