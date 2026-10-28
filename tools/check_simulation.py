"""Differential HDL checks against independent arithmetic and the evaluator."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import random
import subprocess

from combhdl import Component, Const, Output, compile, evaluate
from examples.combinational.operations import expected, operations

ROOT = Path(__file__).resolve().parents[1]


def vectors(width: int) -> list[tuple[int, int, int]]:
    if width <= 4:
        return list(itertools.product(range(1 << width), range(1 << width), range(2)))
    mask = (1 << width) - 1
    boundary = [0, 1, mask // 2, mask // 2 + 1, mask - 1, mask]
    rng = random.Random(20261028)
    return list(itertools.product(boundary, boundary, range(2))) + [
        (rng.randrange(mask + 1), rng.randrange(mask + 1), rng.randrange(2))
        for _ in range(256)
    ]


def testbench(
    component: Component, cases: list[tuple[dict[str, int], dict[str, int]]]
) -> str:
    lines = ["`timescale 1ns/1ps", "module tb;"]
    lines += [f"reg [{p.width - 1}:0] {p.name};" for p in component.inputs]
    lines += [f"wire [{p.width - 1}:0] {p.name};" for p in component.outputs]
    ports = [p.name for p in component.inputs] + [p.name for p in component.outputs]
    lines += [
        f"{component.name} dut (" + ", ".join(f".{p}({p})" for p in ports) + ");",
        "initial begin",
    ]
    for i, (inputs, outputs) in enumerate(cases):
        assert evaluate(component, inputs) == outputs
        lines += [
            f"{p.name} = {p.width}'h{inputs[p.name]:x};" for p in component.inputs
        ]
        lines.append("#1;")
        for p in component.outputs:
            lines.append(
                f'if ({p.name} !== {p.width}\'h{outputs[p.name]:x}) $fatal(1, "vector {i} port {p.name}");'
            )
    lines += ['$display("PASS");', "$finish;", "end", "endmodule", ""]
    return "\n".join(lines)


def run_case(
    sim: str,
    executable: str,
    component: Component,
    cases: list[tuple[dict[str, int], dict[str, int]]],
    output: Path,
) -> dict[str, object]:
    build = output / sim / component.name
    build.mkdir(parents=True, exist_ok=True)
    source = compile(component).verilog
    (build / "design.v").write_text(source)
    tb = testbench(component, cases)
    (build / "tb.v").write_text(tb)
    if sim == "icarus":
        command = [
            executable,
            "-g2012",
            "-s",
            "tb",
            "-o",
            "simulation",
            "design.v",
            "tb.v",
        ]
        run_command = ["vvp", "simulation"]
    else:
        command = [
            executable,
            "--binary",
            "--timing",
            "-Wno-fatal",
            "--top-module",
            "tb",
            "--Mdir",
            "obj",
            "-j",
            "2",
            "design.v",
            "tb.v",
        ]
        run_command = [str(build / "obj/Vtb")]
    with (build / "simulation.log").open("w") as log:
        subprocess.run(
            command, cwd=build, stdout=log, stderr=subprocess.STDOUT, check=True
        )
        subprocess.run(
            run_command, cwd=build, stdout=log, stderr=subprocess.STDOUT, check=True
        )
    print(f"{sim}: {component.name}: {len(cases)} vectors PASS", flush=True)
    return {
        "component": component.name,
        "vectors": len(cases),
        "design_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "testbench_sha256": hashlib.sha256(tb.encode()).hexdigest(),
        "command": command,
        "run_command": run_command,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim", choices=["icarus", "verilator"], required=True)
    parser.add_argument("--executable")
    parser.add_argument("--output", type=Path, default=ROOT / "build/simulation")
    args = parser.parse_args()
    executable = args.executable or (
        "iverilog" if args.sim == "icarus" else "verilator"
    )
    if "/" in executable:
        executable = str(Path(executable).resolve())
    records: list[dict[str, object]] = []
    for width in (1, 4, 17):
        circuit = operations(width)
        cases = [
            ({"a": a, "b": b, "c": c}, expected(width, a, b, c))
            for a, b, c in vectors(width)
        ]
        records.append(
            run_case(args.sim, executable, circuit, cases, args.output.resolve())
        )
    constant = Component("constant_circuit", [], [Output("value", Const(513, 10))])
    records.append(
        run_case(
            args.sim,
            executable,
            constant,
            [({}, {"value": 513})],
            args.output.resolve(),
        )
    )
    version_flag = "-V" if args.sim == "icarus" else "--version"
    version = subprocess.run(
        [executable, version_flag], capture_output=True, text=True, check=True
    ).stdout.splitlines()[0]
    evidence = {"tool": version, "cases": records}
    (args.output / args.sim / "results.json").write_text(
        json.dumps(evidence, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
