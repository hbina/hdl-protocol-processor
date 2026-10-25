"""The Python ISA, the RTL decoder constants and the design document agree."""

import re
from pathlib import Path

from tools.isa import DESIGN, Opcode, render_design

ROOT = Path(__file__).resolve().parents[1]


def test_rtl_opcode_localparams_match_the_isa():
    rtl = (ROOT / "src/protocol_core.v").read_text()
    localparams = {
        name: int(value, 16)
        for name, value in re.findall(
            r"localparam \[3:0\] OP_(\w+)\s*=\s*4'h([0-9A-Fa-f]);", rtl
        )
    }
    assert localparams == {op.name: op.value for op in Opcode}


def test_design_document_encoding_table_is_current():
    text = DESIGN.read_text()
    assert render_design(text) == text, "run: uv run python -m tools.isa --doc"
