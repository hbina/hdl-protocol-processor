"""Compile a trusted Python construction file to artifacts or Verilog stdout."""

import argparse
import json
from pathlib import Path
import runpy
import sys

from . import CompileError, Component, compile
from .ast import format_ast


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--component", default="component")
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output", type=Path, help="write HDL and JSON artifacts")
    destination.add_argument(
        "--stdout", action="store_true", help="print only generated Verilog to stdout"
    )
    args = parser.parse_args()
    try:
        component = runpy.run_path(str(args.source)).get(args.component)
        if not isinstance(component, Component):
            raise CompileError(f"export {args.component!r} must be a Component")
        result = compile(component)
        if args.stdout:
            sys.stdout.write(result.verilog)
            return
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / f"{component.name}.v").write_text(result.verilog)
        (args.output / "ast.txt").write_text(format_ast(component))
        for name, data in (("interface", result.interface), ("report", result.report)):
            (args.output / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n")
    except CompileError as exc:
        parser.exit(1, f"combhdl: {exc}\n")


if __name__ == "__main__":
    main()
