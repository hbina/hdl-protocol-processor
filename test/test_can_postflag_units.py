"""Post-flag counter firmware freshness and real instruction-space limits."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_can_postflag import generate
from generic_call_frontier import assemble as call_assemble

from tools.assembler import assemble


def test_can_postflag_generation_and_capacity():
    here = ROOT / "study/protocol_exploration"
    source = (here / "can_postflag_candidate.asm").read_text()
    raw = (here / "can_postflag_unoptimized_candidate.asm").read_text()
    partial = (here / "can_postflag_partial_compaction_candidate.asm").read_text()
    assert source == generate() and raw == generate(compact=False)
    assert partial == generate(cleanup=False)
    assert len(call_assemble(source)) == 1023
    for text, words in [(raw, 1034), (partial, 1028)]:
        with pytest.raises(
            ValueError, match=f"program contains {words} words; maximum is 1024"
        ):
            call_assemble(text)
    with pytest.raises(ValueError, match="program contains 1023 words; maximum is 128"):
        assemble(source)
