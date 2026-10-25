"""Reproducible firmware and conservative packed USB waveform bounds."""

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "test"))
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_usb_in import generate
from generic_carry_frontier import assemble
from usb_rx_peer import crc16, encode

from tools.assembler import assemble as production_assemble


def test_generated_bidirectional_usb_source_and_capacity():
    source = (ROOT / "study/protocol_exploration/usb_in_candidate.asm").read_text()
    assert source == generate().to_asm()
    assert len(assemble(source)) == 629
    with pytest.raises(ValueError):
        production_assemble(source)


def test_packed_waveform_bound_for_runtime_payloads():
    # At most one stuff bit per six bits: 8 SYNC + 88 packet + 14 stuff
    # + 3 EOP cells =113; four two-bit states fit one byte, so29 bytes suffice.
    assert (8 + 88 + 88 // 6 + 3 + 3) // 4 == 29
    rng = random.Random(0x5041434B)
    for length in range(9):
        for payload in [
            bytes(length),
            b"\xff" * length,
            *[bytes(rng.randrange(256) for _ in range(length)) for _ in range(20)],
        ]:
            for pid in [0xC3, 0x4B]:
                states, _ = encode(bytes([pid]) + payload + crc16(payload))
                assert len(states) <= 113
                assert 192 + (len(states) + 3) // 4 <= 221
