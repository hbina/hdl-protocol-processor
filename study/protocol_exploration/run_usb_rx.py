#!/usr/bin/env python3
"""Protocol frontier experiments on an explicitly counterfactual 512-word model.

All production sources stay unchanged. The model extends generic long branch
addresses: JMP/JFAIL use instruction bit9 for address bit8; JZ/DJNZ use bit11.
No protocol-aware opcode or hardware is added. Actual ASIC assembly is default.
"""

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from isa_variants import assemble_wide512

from tools.assembler import AssemblyError, assemble


def replace_exact(source, old, new, count=1):
    if source.count(old) != count:
        raise RuntimeError(f"source changed; audit study extension: {old}")
    return source.replace(old, new)


def candidate_words(protocol):
    return assemble_wide512((HERE / f"{protocol}_candidate.asm").read_text())


def expanded_source():
    source = (ROOT / "src/protocol_core.v").read_text()
    for old, new in [
        ("program_mem [0:127]", "program_mem [0:511]"),
        ("reg [6:0] pc;", "reg [8:0] pc;"),
        ("reg [6:0]  cfg_address;", "reg [8:0]  cfg_address;"),
    ]:
        source = replace_exact(source, old, new)
    old = "operand_a[2] ? immediate[6:0] : {1'b0, immediate[5:0]}"
    if source.count(old) != 3:
        raise RuntimeError("audit long-branch model extension")
    source = source.replace(
        old, "operand_a[2] ? {operand_a[1], immediate} : {3'b0, immediate[5:0]}", 1
    )
    source = replace_exact(
        source,
        old,
        "operand_a[2] ? {operand_a[3], immediate} : {3'b0, immediate[5:0]}",
        2,
    )
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", choices=["usb_rx"])
    parser.add_argument("--expanded-model", action="store_true")
    parser.add_argument("--test-filter")
    parser.add_argument("--deadline-check", action="store_true")
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
    build = (
        ROOT
        / "test/sim_build"
        / f"{args.protocol}_{'deadline' if args.deadline_check else 'capacity'}512"
    )
    build.mkdir(parents=True, exist_ok=True)
    core = build / "protocol_core_capacity512.v"
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
        HERE / f"{args.protocol}_peer.py",
        HERE / "usb_rx_deadline_peer.py",
        HERE / "build_usb_rx.py",
        HERE / "build_can_rx.py",
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
        test_module="usb_rx_deadline_peer" if args.deadline_check else "usb_rx_peer",
        hdl_toplevel="tb",
        build_dir=build,
        test_dir=build,
        results_xml=str(build / "results.xml"),
        seed=20261024,
        test_filter=args.test_filter,
        extra_env={"WAVE_C_CAPACITY_EXPERIMENT": args.protocol},
    )
    if not Path(result).is_file():
        raise SystemExit("Simulator did not produce results")
    root = ET.parse(result).getroot()
    all_cases = root.findall(".//testcase")
    cases = [c for c in all_cases if c.find("skipped") is None]
    skipped = len(all_cases) - len(cases)
    failed = sum(
        c.find("failure") is not None or c.find("error") is not None for c in cases
    )
    unsuccessful = not cases or failed or (skipped and not args.test_filter)
    if any(
        hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest
        for name, digest in digests.items()
    ):
        raise SystemExit("Sources changed during the experiment")
    record = {
        "date": str(datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date()),
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "protocol": args.protocol,
        "model": "counterfactual512_with_generic_9bit_long_branches",
        "actual_asic_capacity_words": 128,
        "candidate_words": len(candidate_words(args.protocol)),
        "command": f"uv run --locked python study/protocol_exploration/run_usb_rx.py {args.protocol} --expanded-model"
        + (" --deadline-check" if args.deadline_check else "")
        + (f" --test-filter {args.test_filter}" if args.test_filter else ""),
        "passed": len(cases) - failed,
        "failed": failed,
        "skipped": skipped,
        "cases": [c.attrib["name"] for c in cases],
        "source_sha256": digests,
        "results_xml_sha256": hashlib.sha256(Path(result).read_bytes()).hexdigest(),
        "production_rtl_changed": False,
        "physical_fit_verified": False,
        "deadline_check": args.deadline_check,
    }
    (build / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
    if unsuccessful:
        raise SystemExit("Packet-model tests failed; see evidence.json and results.xml")
    print(
        f"{len(cases)} tests passed on 512-word generic model only; actual ASIC capacity stays 128 words."
    )


if __name__ == "__main__":
    main()
