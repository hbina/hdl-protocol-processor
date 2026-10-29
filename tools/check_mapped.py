"""Run the exhaustive board test against the exact newly routed netlist."""

import argparse
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from .run_physical import ROOT, sha256, source_hashes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    provenance = ROOT / "build/physical" / run_dir.name
    manifest = json.loads((provenance / "launch.json").read_text())
    if manifest["run_dir"] != str(run_dir) or manifest["status"] != "finished":
        parser.error(
            "physical run must have completed successfully with recorded provenance"
        )
    if (
        manifest["source_sha256"] != source_hashes()
        or not manifest["sources_unchanged"]
    ):
        parser.error("physical source hashes do not match the current worktree")
    netlist = run_dir / "final/nl/tt_um_combhdl_demo.nl.v"
    relative = str(netlist.relative_to(run_dir))
    if sha256(netlist) != manifest["artifact_sha256"][relative]:
        parser.error("mapped netlist does not match the completed physical run")
    build = ROOT / "test/sim_build/gl" / run_dir.name
    build.mkdir(parents=True, exist_ok=True)
    xml = build / "results.xml"
    if xml.exists():
        xml.unlink()
    command = [
        "uv",
        "run",
        "--locked",
        "make",
        "-B",
        "-C",
        "test",
        "GATES=yes",
        "SIM=icarus",
        f"GATE_NETLIST={netlist}",
        f"SIM_BUILD={build}",
        f"COCOTB_RESULTS_FILE={xml}",
    ]
    env_command = command + [f"PDK_ROOT={ROOT / '.asic-tools/pdk'}"]
    with (provenance / "mapped_simulation.log").open("w") as log:
        subprocess.run(
            env_command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True
        )
    cases = ET.parse(xml).getroot().findall(".//testcase")
    if (
        len(cases) != 1
        or cases[0].get("name") != "exhaustive_wrapper"
        or any(
            cases[0].find(tag) is not None for tag in ("failure", "error", "skipped")
        )
    ):
        raise SystemExit("expected exhaustive_wrapper to pass without skip or failure")
    result = {
        "command": env_command,
        "source_sha256": source_hashes(),
        "netlist_sha256": sha256(netlist),
        "test_source_sha256": {
            name: sha256(ROOT / name)
            for name in ("test/demo.py", "test/tb.v", "test/Makefile")
        },
        "xml_sha256": sha256(xml),
        "test": "demo.exhaustive_wrapper",
        "result": "passed",
        "meaningful_inputs": 512,
        "unused_patterns_per_input": 12,
        "observations": 6144,
    }
    (provenance / "mapped_simulation.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(
        f"Mapped exhaustive wrapper: 6144 observations PASS; evidence in {provenance}"
    )


if __name__ == "__main__":
    main()
