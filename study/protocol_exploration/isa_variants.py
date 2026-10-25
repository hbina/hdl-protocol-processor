"""Study ISA variants, each a typed ``IsaConfig`` rather than a patched assembler.

The variants only widen the production encoding (see ``tools/isa.py``); the
matching widened RTL is still produced by each runner's ``expanded_source``.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.assembler import assemble, labels  # noqa: E402
from tools.isa import (  # noqa: E402
    CALL_FRONTIER,
    CARRY_FRONTIER,
    FRONTIER,
    WIDE256,
    WIDE512,
)


def assemble_wide256(source: str) -> list[int]:
    return assemble(source, WIDE256)


def assemble_wide512(source: str) -> list[int]:
    return assemble(source, WIDE512)


def assemble_frontier(source: str) -> list[int]:
    return assemble(source, FRONTIER)


def assemble_call_frontier(source: str) -> list[int]:
    return assemble(source, CALL_FRONTIER)


def assemble_carry_frontier(source: str) -> list[int]:
    return assemble(source, CARRY_FRONTIER)


def label_addresses(source: str) -> dict[str, int]:
    """Label table of any study program; every variant fits in 1024 words."""

    return labels(source, CARRY_FRONTIER)
