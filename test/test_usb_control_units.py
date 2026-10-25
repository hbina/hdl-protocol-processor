"""Live TX CRC initialization and generated autonomous firmware boundaries."""

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "test"))
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_usb_control import generate as control_source
from build_usb_stream import crc_seed
from build_usb_stream import generate as stream_source
from generic_carry_frontier import assemble
from usb_rx_peer import crc16

from tools.assembler import assemble as production_assemble


def test_live_crc_pid_compensation_against_wire_oracle():
    rng = random.Random(0x53454544)
    for pid in [0xC3, 0x4B]:
        for length in range(9):
            for _ in range(100):
                payload = bytes(rng.randrange(256) for _ in range(length))
                value = crc_seed(pid)
                for byte in bytes([pid]) + payload:
                    value ^= byte
                    for _ in range(8):
                        value = (value >> 1) ^ (0xA001 if value & 1 else 0)
                # Oracle uses polynomial division, independent of the CRC loop.
                assert (value ^ 0xFFFF).to_bytes(2, "little") == crc16(payload)


def test_generated_live_and_control_sources_and_capacity():
    directory = ROOT / "study/protocol_exploration"
    for name, generate, count in [
        ("usb_stream", stream_source, 648),
        ("usb_control", control_source, 776),
    ]:
        source = (directory / f"{name}_candidate.asm").read_text()
        assert source == generate().to_asm()
        assert len(assemble(source)) == count
        with pytest.raises(ValueError):
            production_assemble(source)
