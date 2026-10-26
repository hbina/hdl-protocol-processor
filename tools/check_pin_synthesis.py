"""Synthesize the wrapper and five pin-count configurations; no physical-fit claim."""

from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("wrapper", None, None),
    ("1_1", 1, 1),
    ("8_8", 8, 8),
    ("15_16", 15, 16),
    ("17_9", 17, 9),
    ("256_256", 256, 256),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yosys", default="yosys", help="native or yowasp-yosys executable"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "test/sim_build/pin_synthesis"
    )
    args = parser.parse_args()
    executable = args.yosys
    if "/" in executable:
        executable = str(Path(executable).resolve())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for name, inputs, outputs in CASES:
        build = output / name
        build.mkdir(exist_ok=True)
        top = "tt_um_protocol_emulator" if inputs is None else "protocol_core"
        script = "read_verilog -sv src/protocol_core.v src/project.v; "
        if inputs is not None:
            script += f"chparam -set INPUT_PINS {inputs} -set OUTPUT_PINS {outputs} protocol_core; "
        script += f'synth -top {top} -noabc; check -assert; tee -o "{build}/stat.json" stat -json'
        command = [executable, "-p", script]
        with (build / "synthesis.log").open("w") as log:
            result = subprocess.run(
                command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=os.environ
            )
        record: dict[str, object] = {
            "configuration": name,
            "command": command,
            "exit_code": result.returncode,
        }
        if result.returncode == 0:
            record["statistics"] = json.loads((build / "stat.json").read_text())[
                "design"
            ]
        records.append(record)
        evidence = {
            "sources": {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [ROOT / "src/protocol_core.v", ROOT / "src/project.v"]
            },
            "results": records,
        }
        (output / "results.json").write_text(json.dumps(evidence, indent=2) + "\n")
        if result.returncode:
            raise SystemExit(f"{name}: synthesis failed; see {build}/synthesis.log")
        print(f"{name}: PASS", flush=True)


if __name__ == "__main__":
    main()
