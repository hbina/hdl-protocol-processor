"""RX error-flag firmware freshness and reproduced code-space boundaries."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_can_rx_flags import generate as unoptimized
from build_can_rx_flags_compact import generate
from generic_call_frontier import assemble as call_assemble

from tools.assembler import assemble


def test_can_rx_flags_generation_and_capacity():
    source = (
        ROOT / "study/protocol_exploration/can_rx_flags_compact_candidate.asm"
    ).read_text()
    large = (ROOT / "study/protocol_exploration/can_rx_flags_candidate.asm").read_text()
    assert source == generate() and large == unoptimized()
    assert len(call_assemble(source)) == 1021
    with pytest.raises(
        ValueError, match="program contains 1069 words; maximum is 1024"
    ):
        call_assemble(large)
    with pytest.raises(ValueError, match="program contains 1021 words; maximum is 128"):
        assemble(source)
