#!/usr/bin/env python3
"""Reproduce I2C capacity failure, or test a counterfactual 256-word RTL model.

Default: assemble with the actual 128-word limit (expected nonzero exit).
--expanded-model: change only a generated copy's instruction store, PC,
loader cursor and long branch width. Production RTL and assembler stay intact.
This is NOT a supported ASIC configuration or a physical implementation result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from isa_variants import assemble_wide256

from tools.assembler import AssemblyError, assemble


def candidate_words():
    return assemble_wide256((HERE / "i2c_candidate.asm").read_text())


def expanded_source():
    source = (ROOT / "src/protocol_core.v").read_text()
    substitutions = {
        "program_mem [0:127]": ("program_mem [0:255]", 1),
        "reg [6:0] pc;": ("reg [7:0] pc;", 1),
        "reg [6:0]  cfg_address;": ("reg [7:0]  cfg_address;", 1),
        "operand_a[2] ? immediate[6:0] : {1'b0, immediate[5:0]}": (
            "operand_a[2] ? immediate : {2'b0, immediate[5:0]}",
            3,
        ),
    }
    for old, (new, count) in substitutions.items():
        if source.count(old) != count:
            raise RuntimeError(
                f"core changed; audit capacity experiment replacement: {old}"
            )
        source = source.replace(old, new)
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expanded-model", action="store_true")
    parser.add_argument("--test-filter")
    args = parser.parse_args()
    if not args.expanded_model:
        try:
            assemble((HERE / "i2c_candidate.asm").read_text())
        except AssemblyError as error:
            parser.exit(1, f"Actual ASIC capacity: {error}\n")
        parser.exit(
            0, "Candidate fits actual capacity; reevaluate the recorded blocker.\n"
        )

    from cocotb_tools.runner import get_runner

    sys.path.insert(0, str(ROOT / "test"))
    build = ROOT / "test/sim_build/i2c_capacity256"
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
        HERE / "i2c_candidate.asm",
        HERE / "i2c_peer.py",
        Path(__file__),
        ROOT / "test/test.py",
        ROOT / "tools/assembler.py",
        ROOT / "tools/isa.py",
        ROOT / "tools/program.py",
        HERE / "isa_variants.py",
        HERE / "fragments.py",
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
        test_module="i2c_peer",
        hdl_toplevel="tb",
        build_dir=build,
        test_dir=build,
        results_xml=str(build / "results.xml"),
        seed=20261024,
        test_filter=args.test_filter,
        extra_env={"I2C_CAPACITY_EXPERIMENT": "256"},
    )
    if not Path(result).is_file():
        raise SystemExit(
            "Simulator did not produce results; inspect the initialization error above"
        )
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
        raise SystemExit("I2C capacity-model tests failed or were skipped")
    if any(
        hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest
        for name, digest in digests.items()
    ):
        raise SystemExit("Sources changed during the capacity experiment")
    record = {
        "date": "2026-10-24",
        "model": "counterfactual_256_word_instruction_store",
        "actual_asic_capacity_words": 128,
        "candidate_words": len(candidate_words()),
        "command": "uv run --locked python study/protocol_exploration/run_i2c.py --expanded-model"
        + (f" --test-filter {args.test_filter}" if args.test_filter else ""),
        "passed": len(cases),
        "skipped": skipped,
        "cases": [c.attrib["name"] for c in cases],
        "source_sha256": digests,
        "results_xml_sha256": hashlib.sha256(Path(result).read_bytes()).hexdigest(),
        "production_rtl_changed": False,
        "physical_fit_verified": False,
        "note": "Runtime-store capabilities intentionally remain the unmodified 128-word ABI; do not use this model as a board image.",
    }
    (build / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
    print(
        f"{len(cases)} tests passed on expanded model only; actual ASIC capacity remains 128 words."
    )


if __name__ == "__main__":
    main()
