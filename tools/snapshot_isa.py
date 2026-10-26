"""Snapshot only active standalone firmware; historical encodings stay separate."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from tools.assembler import assemble_image

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "test/golden/pin_words.json"


def snapshot() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for source in sorted((ROOT / "firmware").glob("*.asm")):
        image = assemble_image(source.read_text())
        result[str(source.relative_to(ROOT))] = {
            "words": image.words,
            "symbols": image.symbols,
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="replace the active golden snapshot"
    )
    args = parser.parse_args()
    text = json.dumps(snapshot(), indent=2) + "\n"
    if args.write:
        GOLDEN.write_text(text)
    elif GOLDEN.read_text() != text:
        raise SystemExit("active firmware snapshot changed; review then use --write")


if __name__ == "__main__":
    main()
