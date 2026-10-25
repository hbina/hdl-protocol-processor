"""Retain tail compaction, actual capacity and the unsafe-idle comparison."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_can_tail_compact import generate
from generic_call_frontier import assemble as model_assemble

from tools.assembler import assemble


def test_can_tail_compaction_freshness_and_capacity():
    here = ROOT / "study/protocol_exploration"
    source = (here / "can_tail_compact_candidate.asm").read_text()
    unsafe = (here / "can_tail_compact_unsafe_candidate.asm").read_text()
    assert (
        source == generate().to_asm() and unsafe == generate(safe_idle=False).to_asm()
    )
    assert source != unsafe
    assert len(model_assemble(source)) == len(model_assemble(unsafe)) == 1024
    with pytest.raises(ValueError, match="program contains 1024 words; maximum is 128"):
        assemble(source)
