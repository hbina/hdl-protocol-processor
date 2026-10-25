#!/usr/bin/env python3
"""Isolated generic1024x18/eight-register experiment; production unchanged."""

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
from generic_call_frontier import assemble as frontier_assemble
from generic_call_frontier import expanded_source

from tools.assembler import AssemblyError, assemble


def candidate_words(protocol):
    return frontier_assemble((HERE / "can_flag_compact_candidate.asm").read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", choices=["can_flag_compact"])
    parser.add_argument("--expanded-model", action="store_true")
    parser.add_argument("--test-filter")
    parser.add_argument(
        "--suite", choices=["flag", "postflag", "rx_flags", "fault"], default="flag"
    )
    parser.add_argument(
        "--prior-monitor",
        action="store_true",
        help="Retain the1023-word earlier flag monitor",
    )
    args = parser.parse_args()
    candidate = HERE / (
        "can_postflag_candidate.asm"
        if args.prior_monitor
        else "can_flag_compact_candidate.asm"
    )
    if not args.expanded_model:
        try:
            assemble(candidate.read_text())
        except AssemblyError as error:
            parser.exit(1, f"Actual ASIC capacity: {error}\n")
        parser.exit(
            0, "Candidate fits actual capacity; reevaluate any recorded blocker.\n"
        )
    # Reject oversized generic-model firmware before building/running RTL.
    frontier_assemble(candidate.read_text())
    from cocotb_tools.runner import get_runner

    sys.path.insert(0, str(ROOT / "test"))
    build = (
        ROOT
        / "test/sim_build"
        / f"{args.protocol}{'_' + args.suite if args.suite != 'flag' else ''}{'_fixed' if args.prior_monitor else ''}_call_frontier1024"
    )
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
    tracked = sources + [
        ROOT / "src/protocol_core.v",
        candidate,
        HERE / "can_flag_bit_peer.py",
        HERE / "frontier_peer.py",
        HERE / "build_can_flag_compact.py",
        HERE / "build_can_flag_bit.py",
        HERE / "build_can_postflag.py",
        HERE / "can_postflag_peer.py",
        HERE / "build_can_rx_flags.py",
        HERE / "build_can_rx_flags_compact.py",
        HERE / "can_rx_flags_peer.py",
        HERE / "build_can_fault_equal.py",
        HERE / "can_fault_equal_peer.py",
        HERE / "can_resync_peer.py",
        HERE / "build_can_fault.py",
        HERE / "build_can_resync.py",
        HERE / "build_can_winner.py",
        HERE / "can_winner_peer.py",
        HERE / "generic_call_frontier.py",
        HERE / "build_can_recovery.py",
        HERE / "can_recovery_peer.py",
        HERE / "generic_frontier.py",
        HERE / "build_can_rx.py",
        HERE / "build_can_tx.py",
        HERE / "build_can_duplex.py",
        HERE / "build_can_frontier.py",
        HERE / "can_peer.py",
        HERE / "can_tx_peer.py",
        HERE / "run_can.py",
        HERE / "run_can_tx.py",
        Path(__file__),
        ROOT / "test/test.py",
        ROOT / "tools/assembler.py",
        ROOT / "tools/runtime.py",
        HERE / "run_can.py",
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
    test_module, env_prefix = {
        "flag": ("can_flag_bit_peer", "CAN_FLAG_BIT"),
        "postflag": ("can_postflag_peer", "CAN_POSTFLAG"),
        "rx_flags": ("can_rx_flags_peer", "CAN_RX_FLAGS"),
        "fault": ("can_fault_equal_peer", "CAN_FAULT_EQUAL"),
    }[args.suite]
    environment = {
        env_prefix + "_EXPERIMENT": "1",
        env_prefix + "_SOURCE": str(candidate),
    }
    if args.suite == "fault":
        environment["CAN_FAULT_SOURCE"] = str(candidate)
    result = runner.test(
        test_module=test_module,
        hdl_toplevel="tb",
        build_dir=build,
        test_dir=build,
        results_xml=str(build / "results.xml"),
        seed=20261024,
        test_filter=args.test_filter,
        extra_env=environment,
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
    if any(
        hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest
        for name, digest in digests.items()
    ):
        raise SystemExit("Sources changed during the experiment")
    record = {
        "date": str(datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date()),
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "protocol": args.protocol,
        "model": "counterfactual1024x18_eight_registers_leaf_call",
        "actual_asic_capacity_words": 128,
        "model_registers": 8,
        "model_instruction_bits": 18,
        "candidate_words": len(frontier_assemble(candidate.read_text())),
        "command": f"uv run --locked python study/protocol_exploration/run_can_flag_compact.py {args.protocol} --expanded-model"
        + (" --prior-monitor" if args.prior_monitor else "")
        + (f" --suite {args.suite}" if args.suite != "flag" else "")
        + (f" --test-filter {args.test_filter}" if args.test_filter else ""),
        "passed": len(cases) - failed,
        "failed": failed,
        "skipped": skipped,
        "cases": [c.attrib["name"] for c in cases],
        "source_sha256": digests,
        "results_xml_sha256": hashlib.sha256(Path(result).read_bytes()).hexdigest(),
        "production_rtl_changed": False,
        "physical_fit_verified": False,
    }
    (build / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
    if not cases or failed or (skipped and not args.test_filter):
        raise SystemExit("Model tests failed or were skipped; provenance saved")
    print(
        f"{len(cases)} tests passed on 1024x18/eight-register generic model only; actual ASIC capacity stays 128 words."
    )


if __name__ == "__main__":
    main()
