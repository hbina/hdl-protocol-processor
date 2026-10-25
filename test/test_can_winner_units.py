"""Winner-reception firmware generation and actual production capacity."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_can_winner import generate
from generic_frontier import assemble as frontier_assemble

from tools.assembler import assemble


def test_can_winner_generation_and_capacity():
    source = (ROOT / "study/protocol_exploration/can_winner_candidate.asm").read_text()
    assert source == generate().to_asm()
    assert len(frontier_assemble(source)) == 811
    with pytest.raises(ValueError, match="program contains 811 words; maximum is 128"):
        assemble(source)
