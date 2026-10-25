#!/usr/bin/env python3
"""Reproduce validated JTAG capacity failure and run the explicit256-word model.

Like the I2C study, this changes only a generated model. No production RTL or
assembler setting is changed. Default assembly uses the real 128-word limit.
"""

import argparse
import hashlib
import importlib.util
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from run_i2c import expanded_source

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from tools.assembler import AssemblyError, assemble


def candidate_words(protocol):
    spec = importlib.util.spec_from_file_location(
        "wave_b_assembler", ROOT / "tools/assembler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PROGRAM_WORDS = 256
    return module.assemble((HERE / f"{protocol}_candidate.asm").read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", choices=["jtag_runtime"])
    parser.add_argument("--expanded-model", action="store_true")
    parser.add_argument("--test-filter")
    args = parser.parse_args()
    candidate = HERE / f"{args.protocol}_candidate.asm"
    if not args.expanded_model:
        try:
            assemble(candidate.read_text())
        except AssemblyError as error:
            parser.exit(1, f"Actual ASIC capacity: {error}\n")
        parser.exit(
            0, "Candidate fits actual capacity; reevaluate any recorded blocker.\n"
        )
    from cocotb_tools.runner import get_runner

    sys.path.insert(0, str(ROOT / "test"))
    build = ROOT / "test/sim_build" / f"{args.protocol}_capacity256"
    build.mkdir(parents=True, exist_ok=True)
    core = build / "protocol_core_capacity256.v"
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
    tracked = sources + [
        ROOT / "src/protocol_core.v",
        candidate,
        ROOT / "test/test_jtag_runtime.py",
        HERE / "build_jtag_runtime.py",
        ROOT / "firmware/jtag_probe.asm",
        ROOT / "firmware/runtime.asm",
        ROOT / "test/test_jtag_probe.py",
        Path(__file__),
        HERE / "run_i2c.py",
        ROOT / "test/test.py",
        ROOT / "tools/assembler.py",
        ROOT / "tools/runtime.py",
    ]
    digests = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in tracked
    }
    runner = get_runner("icarus")
    runner.build(
        sources=sources,
        hdl_toplevel="tb",
        build_dir=build,
        build_args=["-g2012"],
        always=True,
    )
    result = runner.test(
        test_module="test_jtag_runtime",
        hdl_toplevel="tb",
        build_dir=build,
        test_dir=build,
        results_xml=str(build / "results.xml"),
        seed=20261025,
        test_filter=args.test_filter,
        extra_env={"JTAG_RUNTIME_EXPERIMENT": "1"},
    )
    if not Path(result).is_file():
        raise SystemExit("Simulator did not produce results")
    root = ET.parse(result).getroot()
    all_cases = root.findall(".//testcase")
    cases = [c for c in all_cases if c.find("skipped") is None]
    skipped = len(all_cases) - len(cases)
    if (
        not cases
        or root.findall(".//failure")
        or root.findall(".//error")
        or (skipped and not args.test_filter)
    ):
        raise SystemExit("Capacity-model tests failed or were skipped")
    if any(
        hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest
        for name, digest in digests.items()
    ):
        raise SystemExit("Sources changed during the capacity experiment")
    record = {
        "date": "2026-10-25",
        "protocol": args.protocol,
        "model": "counterfactual_256_word_instruction_store",
        "actual_asic_capacity_words": 128,
        "model_registers": 4,
        "model_instruction_bits": 16,
        "candidate_words": len(candidate_words(args.protocol)),
        "command": f"uv run --locked python study/protocol_exploration/run_jtag_runtime.py {args.protocol} --expanded-model"
        + (f" --test-filter {args.test_filter}" if args.test_filter else ""),
        "passed": len(cases),
        "skipped": skipped,
        "cases": [c.attrib["name"] for c in cases],
        "source_sha256": digests,
        "results_xml_sha256": hashlib.sha256(Path(result).read_bytes()).hexdigest(),
        "production_rtl_changed": False,
        "physical_fit_verified": False,
    }
    (build / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
    print(
        f"{len(cases)} tests passed on expanded model only; actual ASIC capacity remains 128 words."
    )


if __name__ == "__main__":
    main()
