"""Execute a trusted Python construction file and write reproducible artifacts."""

import argparse
import json
from pathlib import Path
import runpy

from . import CompileError, Component, compile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--component", default="component")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        component = runpy.run_path(str(args.source)).get(args.component)
        if not isinstance(component, Component):
            raise CompileError(f"export {args.component!r} must be a Component")
        result = compile(component)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / f"{component.name}.v").write_text(result.verilog)
        for name, data in (("interface", result.interface), ("report", result.report)):
            (args.output / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n")
    except CompileError as exc:
        parser.exit(1, f"combhdl: {exc}\n")


if __name__ == "__main__":
    main()
