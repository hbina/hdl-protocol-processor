"""Generic synthesis and structural no-storage checks; no physical-fit claim."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from combhdl import compile
from examples.combinational.operations import operations

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yosys", default="yosys")
    parser.add_argument("--output", type=Path, default=ROOT / "build/synthesis")
    args = parser.parse_args()
    executable = args.yosys
    if "/" in executable:
        executable = str(Path(executable).resolve())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    version = subprocess.run(
        [executable, "-V"], capture_output=True, text=True, check=True
    ).stdout.strip()
    records: list[dict[str, object]] = []
    cases = [
        ("tt_um_combhdl_demo", [ROOT / "src/project.v", ROOT / "src/combhdl_demo.v"])
    ]
    for width in (1, 4, 17):
        circuit = operations(width)
        path = output / f"{circuit.name}.v"
        path.write_text(compile(circuit).verilog)
        cases.append((circuit.name, [path]))
    for top, sources in cases:
        build = output / top
        build.mkdir(exist_ok=True)
        # The netlist whitelist below admits only combinational bit primitives.
        # Remove Yosys hierarchy debug metadata before counting logic cells.
        script = "read_verilog " + " ".join(f'"{s}"' for s in sources) + "; "
        script += f"synth -top {top} -flatten -noabc; check -assert; scc -expect 0; "
        script += "delete t:$scopeinfo; "
        script += (
            f'tee -o "{build}/stat.json" stat -json; write_json "{build}/netlist.json"'
        )
        command = [executable, "-p", script]
        with (build / "synthesis.log").open("w") as log:
            subprocess.run(
                command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True
            )
        stat = json.loads((build / "stat.json").read_text())
        netlist = json.loads((build / "netlist.json").read_text())
        allowed = {
            "$_AND_",
            "$_OR_",
            "$_XOR_",
            "$_NOT_",
            "$_MUX_",
            "$_XNOR_",
            "$_NAND_",
            "$_NOR_",
            "$_ANDNOT_",
            "$_ORNOT_",
        }
        cells = netlist["modules"][top]["cells"]
        assert all(cell["type"] in allowed for cell in cells.values()), (
            "noncombinational cell found"
        )
        assert not netlist["modules"][top].get("memories"), "memory found"
        records.append(
            {
                "top": top,
                "command": command,
                "source_sha256": {
                    s.name: hashlib.sha256(s.read_bytes()).hexdigest() for s in sources
                },
                "statistics": stat,
                "storage_cells": 0,
                "combinational_loops": 0,
            }
        )
        print(
            f"{top}: {len(cells)} generic cells, no storage or loops PASS", flush=True
        )
    (output / "results.json").write_text(
        json.dumps({"tool": version, "cases": records}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
