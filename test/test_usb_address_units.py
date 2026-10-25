"""Token CRC5 address constants and reproducible reset/address firmware."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "test"))
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_usb_address import generate, token_crc_byte
from generic_carry_frontier import assemble
from usb_out_peer import token

from tools.assembler import assemble as production_assemble


def test_address_crc5_basis_against_independent_token_oracle():
    assert token_crc_byte(0) == 16
    basis = [token_crc_byte(1 << bit) ^ 16 for bit in range(7)]
    for address in range(128):
        affine = 16
        for bit in range(7):
            if address & (1 << bit):
                affine ^= basis[bit]
        assert affine == token_crc_byte(address) == token(address, 0)[2]


def test_generated_reset_address_source_and_capacity():
    source = (ROOT / "study/protocol_exploration/usb_address_candidate.asm").read_text()
    assert source == generate().to_asm()
    assert len(assemble(source)) == 921
    with pytest.raises(ValueError):
        production_assemble(source)
