"""Descriptor ABI, generated enumeration firmware and capacity boundaries."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study/protocol_exploration"))
from build_usb_enum import CONFIG, DEVICE, generate
from generic_carry_frontier import assemble

from tools.assembler import assemble as production_assemble


def test_descriptor_image_layout_and_constant_data():
    saved = json.loads(
        (ROOT / "study/protocol_exploration/usb_enum_constants.json").read_text()
    )
    assert bytes(saved["device"]) == DEVICE and bytes(saved["configuration"]) == CONFIG
    assert len(DEVICE) == DEVICE[0] == 18 and DEVICE[1] == 1
    assert DEVICE[7] == 8 and DEVICE[14:17] == bytes(3) and DEVICE[17] == 1
    assert len(CONFIG) == int.from_bytes(CONFIG[2:4], "little") == 18
    assert CONFIG[:2] == bytes([9, 2]) and CONFIG[4:6] == bytes([1, 1])
    assert CONFIG[9:11] == bytes([9, 4]) and CONFIG[13] == 0  # EP0 only
    assert CONFIG[14] == 0xFF  # vendor interface
    parameter_bytes = 41 + len(DEVICE) + len(CONFIG)
    assert parameter_bytes == 77 and parameter_bytes <= 128


def test_generated_enumeration_sources_and_capacity():
    directory = ROOT / "study/protocol_exploration"
    for name, pipeline, count in [
        ("usb_enum", True, 1012),
        ("usb_enum_unoptimized", False, 991),
    ]:
        source = (directory / f"{name}_candidate.asm").read_text()
        assert source == generate(pipeline).to_asm()
        assert len(assemble(source)) == count
        with pytest.raises(ValueError):
            production_assemble(source)
