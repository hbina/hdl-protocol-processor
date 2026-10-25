#!/usr/bin/env python3
"""Record every checked-in program's encoding under every ISA variant.

The snapshot is the refactoring guard for the instruction model: each source
is assembled by each variant, and either a digest of the words or the exact
error message is stored. test/test_isa_golden.py compares against it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "study/protocol_exploration"
GOLDEN = ROOT / "test/golden/isa_words.json"


def variant_assemblers() -> dict[str, Callable[[str], list[int]]]:
    """Return the assembler used by each ISA variant, keyed by variant name."""

    from tools.assembler import assembler_for
    from tools.isa import CONFIGS

    return {name: assembler_for(cfg) for name, cfg in CONFIGS.items()}


def sources() -> list[Path]:
    return sorted((ROOT / "firmware").glob("*.asm")) + sorted(STUDY.glob("*.asm"))


def digest(words: list[int]) -> str:
    return hashlib.sha256(",".join(f"{w:05x}" for w in words).encode()).hexdigest()


def snapshot() -> dict[str, dict[str, object]]:
    assemblers = variant_assemblers()
    result: dict[str, dict[str, object]] = {}
    for path in sources():
        text = path.read_text()
        entry: dict[str, object] = {
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()
        }
        for name, assemble in assemblers.items():
            try:
                words = assemble(text)
            except ValueError as exc:
                entry[name] = {"error": str(exc)}
            else:
                entry[name] = {"words": len(words), "sha256": digest(words)}
        result[str(path.relative_to(ROOT))] = entry
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=GOLDEN)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
