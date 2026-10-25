"""CAN receive phase firmware freshness and production-capacity evidence."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_can_resync import generate
from generic_frontier import assemble as frontier_assemble

from tools.assembler import assemble


def test_can_resync_generation_and_capacity():
    source = (ROOT / "study/protocol_exploration/can_resync_candidate.asm").read_text()
    assert source == generate().to_asm()
    assert len(frontier_assemble(source)) == 819
    with pytest.raises(ValueError, match="program contains 819 words; maximum is 128"):
        assemble(source)
