#!/usr/bin/env python3
"""UART runtime contract on an isolated generic eight-register model."""

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from generic_frontier import ROOT, assemble, expanded_source

from tools.assembler import AssemblyError
from tools.assembler import assemble as production_assemble

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expanded-model", action="store_true")
    parser.add_argument("--test-filter")
    args = parser.parse_args()
    candidate = HERE / "uart_runtime_candidate.asm"
    if not args.expanded_model:
        try:
            production_assemble(candidate.read_text())
        except AssemblyError as error:
            parser.exit(1, f"Actual ASIC capacity: {error}\n")
        parser.exit(0, "Candidate fits production; reevaluate blocker.\n")
    from cocotb_tools.runner import get_runner

    sys.path.insert(0, str(ROOT / "test"))
    build = ROOT / "test/sim_build/uart_runtime_frontier1024"
    build.mkdir(parents=True, exist_ok=True)
    core = build / "protocol_core_frontier1024.v"
    core.write_text(expanded_source())
    sources = [
        ROOT / "src" / name
        for name in [
            "project.v",
            "runtime_fifo.v",
            "runtime_store.v",
            "runtime_bridge.v",
        ]
    ] + [core, ROOT / "test/tb.v"]
    tracked = (
        sources
        + [
            ROOT / name
            for name in [
                "src/protocol_core.v",
                "test/test.py",
                "test/test_uart_probe.py",
                "test/test_uart_runtime.py",
                "tools/runtime.py",
                "tools/assembler.py",
                "tools/isa.py",
                "tools/program.py",
                "study/protocol_exploration/isa_variants.py",
                "study/protocol_exploration/fragments.py",
                "study/protocol_exploration/build_can_rx.py",
                "study/protocol_exploration/generic_frontier.py",
                "study/protocol_exploration/build_uart_runtime.py",
            ]
        ]
        + [candidate, Path(__file__)]
    )
    fingerprints = {str(p.relative_to(ROOT)): sha(p) for p in tracked}
    runner = get_runner("icarus")
    runner.build(
        sources=sources,
        hdl_toplevel="tb",
        build_dir=build,
        build_args=["-g2012"],
        always=True,
    )
    xml = Path(
        runner.test(
            test_module="test_uart_runtime",
            hdl_toplevel="tb",
            build_dir=build,
            test_dir=build,
            results_xml=str(build / "results.xml"),
            seed=20261025,
            test_filter=args.test_filter,
            extra_env={"UART_RUNTIME_EXPERIMENT": "1"},
        )
    )
    tree = ET.parse(xml).getroot()
    all_cases = tree.findall(".//testcase")
    cases = [c for c in all_cases if c.find("skipped") is None]
    skipped = len(all_cases) - len(cases)
    if (
        not cases
        or tree.findall(".//failure")
        or tree.findall(".//error")
        or (skipped and not args.test_filter)
    ):
        raise SystemExit("UART runtime model tests failed or were skipped")
    for filename, digest in fingerprints.items():
        if sha(ROOT / filename) != digest:
            raise SystemExit(f"Source changed during run: {filename}")
    record = {
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "model": "counterfactual1024x18_eight_registers",
        "candidate_words": len(assemble(candidate.read_text())),
        "production_capacity_words": 128,
        "production_rtl_changed": False,
        "physical_fit_verified": False,
        "passed": len(cases),
        "skipped": skipped,
        "cases": [c.attrib["name"] for c in cases],
        "command": "uv run --locked python study/protocol_exploration/run_uart_runtime.py --expanded-model"
        + (f" --test-filter {args.test_filter}" if args.test_filter else ""),
        "source_sha256": fingerprints,
        "results_xml_sha256": sha(xml),
    }
    (build / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"{len(cases)} UART runtime tests passed on isolated generic model only.")


if __name__ == "__main__":
    main()
