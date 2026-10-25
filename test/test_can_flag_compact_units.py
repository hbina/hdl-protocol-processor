"""Compact flag-bit firmware freshness, model fit and real ASIC size failure."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_can_flag_compact import generate
from generic_call_frontier import assemble as model_assemble

from tools.assembler import assemble


def test_flag_bit_compaction_and_capacity():
    source = (
        ROOT / "study/protocol_exploration/can_flag_compact_candidate.asm"
    ).read_text()
    assert source == generate().to_asm()
    assert len(model_assemble(source)) == 1024
    with pytest.raises(ValueError, match="program contains 1024 words; maximum is 128"):
        assemble(source)
