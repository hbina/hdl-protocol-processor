"""Regenerate the checked-in Tiny Tapeout demonstration, or reject stale HDL."""

import argparse
from pathlib import Path

from combhdl import compile
from examples.combinational.demo import demo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / "src/combhdl_demo.v"
    generated = compile(demo).verilog
    if args.write:
        path.write_text(generated)
    elif not path.exists() or path.read_text() != generated:
        raise SystemExit(
            "src/combhdl_demo.v is stale: run uv run --locked python -m tools.check_generated --write"
        )
    print("Generated demonstration: PASS")


if __name__ == "__main__":
    main()
