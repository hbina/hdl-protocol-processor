"""Generic subroutine encoding and independent checks of fixed CRC syndromes."""

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "test"))
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_usb_live import constants, crc, generate
from generic_call_frontier import assemble
from usb_rx_peer import crc16

from tools.assembler import assemble as legacy_assemble


def test_generic_call_encoding_and_compatibility():
    assert assemble("CALL 0\nCALL 1023\nRET") == [0x0400, 0x07FF, 0x0800]
    for source in ["CALL 1024", "CALL -1", "CALL", "RET 1"]:
        with pytest.raises(ValueError):
            assemble(source)
    for path in (ROOT / "firmware").glob("*.asm"):
        assert assemble(path.read_text()) == legacy_assemble(path.read_text()), path


def test_crc_syndromes_for_arbitrary_payloads():
    # CRC bytes come from the independent polynomial-division wire oracle.
    # The table is constant across payload contents, not host-generated FCS.
    table = constants()
    rng = random.Random(0x435243)
    for mode, pid in enumerate([0xC3, 0x4B]):
        for length in range(9):
            expected = int.from_bytes(
                bytes(table[mode * 18 + length * 2 :][:2]), "little"
            )
            for _ in range(100):
                payload = bytes(rng.randrange(256) for _ in range(length))
                assert crc(bytes([pid]) + payload + crc16(payload)) == expected


def test_crc_syndromes_reject_every_single_data_crc_bit_error():
    table = constants()
    payload = b"\xff\x00\x55\xaa\x01\x80\x7f\xfe"
    for mode, pid in enumerate([0xC3, 0x4B]):
        expected = int.from_bytes(bytes(table[mode * 18 + 16 :][:2]), "little")
        packet = bytes([pid]) + payload + crc16(payload)
        for index in range(8, len(packet) * 8):
            corrupted = bytearray(packet)
            corrupted[index // 8] ^= 1 << (index % 8)
            assert crc(corrupted) != expected


def test_generated_program_and_capacity_boundary():
    directory = ROOT / "study/protocol_exploration"
    shared = (directory / "usb_live_candidate.asm").read_text()
    inline = (directory / "usb_live_inline_candidate.asm").read_text()
    assert generate() == shared and generate(False) == inline
    assert len(assemble(shared)) == 947
    with pytest.raises(
        ValueError, match="program contains 1221 words; maximum is 1024"
    ):
        assemble(inline)
    with pytest.raises(ValueError, match="program contains 947 words; maximum is 128"):
        legacy_assemble(shared)
