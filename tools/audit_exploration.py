#!/usr/bin/env python3
"""Audit recorded experiment/source integrity and reproduce capacity failures.

Success proves only these checks, not protocol acceptance or physical fit.
Run from a checkout retaining the referenced simulator artifacts.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORDS = [
    ("production_probes", "protocol_probe_results", ["rtl"], "test/results.xml"),
    (
        "uart_runtime",
        "uart_runtime_results",
        ["model"],
        "test/sim_build/uart_runtime_frontier1024/results.xml",
    ),
    (
        "jtag_runtime",
        "jtag_runtime_results",
        ["model"],
        "test/sim_build/jtag_runtime_capacity256/results.xml",
    ),
    ("i2c", "i2c_capacity_results", [], "test/sim_build/i2c_capacity256/results.xml"),
    (
        "swd",
        "wave_b_results",
        ["capacity_models", "swd"],
        "test/sim_build/swd_capacity256/results.xml",
    ),
    (
        "ps2",
        "wave_b_results",
        ["capacity_models", "ps2"],
        "test/sim_build/ps2_capacity256/results.xml",
    ),
    (
        "ethernet",
        "ethernet_capacity_results",
        [],
        "test/sim_build/ethernet_capacity512/results.xml",
    ),
    (
        "can_combined",
        "frontier_results",
        ["focused_model"],
        "test/sim_build/can_duplex_frontier1024/results.xml",
    ),
    (
        "can_ack_recovery",
        "can_ack_recovery_results",
        ["model"],
        "test/sim_build/can_recovery_frontier1024/results.xml",
    ),
    (
        "can_winner",
        "can_winner_results",
        ["model"],
        "test/sim_build/can_winner_frontier1024/results.xml",
    ),
    (
        "can_resync",
        "can_resync_results",
        ["model"],
        "test/sim_build/can_resync_frontier1024/results.xml",
    ),
    (
        "can_fault_state",
        "can_fault_state_results",
        ["model"],
        "test/sim_build/can_fault_equal_call_frontier1024/results.xml",
    ),
    (
        "can_receive_flags",
        "can_receive_flags_results",
        ["model"],
        "test/sim_build/can_rx_flags_call_frontier1024/results.xml",
    ),
    (
        "can_postflag",
        "can_postflag_results",
        ["model"],
        "test/sim_build/can_postflag_call_frontier1024/results.xml",
    ),
    (
        "can_flag_restart",
        "can_flag_compact_results",
        ["model"],
        "test/sim_build/can_flag_restart_call_frontier1024/results.xml",
    ),
    (
        "can_flag_postflag_regression",
        "can_flag_compact_results",
        ["postflag_regression"],
        "test/sim_build/can_flag_compact_postflag_call_frontier1024/results.xml",
    ),
    (
        "usb_enumeration",
        "usb_enumeration_results",
        ["model"],
        "test/sim_build/usb_enum_carry_frontier1024/results.xml",
    ),
]
CAPACITY = [
    ("uart_runtime", "run_uart_runtime.py", [], 251),
    ("jtag_runtime", "run_jtag_runtime.py", ["jtag_runtime"], 198),
    ("i2c", "run_i2c.py", [], 249),
    ("swd", "run_wave_b.py", ["swd"], 230),
    ("ps2", "run_wave_b.py", ["ps2"], 188),
    ("ethernet", "run_wave_c.py", ["ethernet"], 280),
    ("can", "run_frontier.py", ["can_duplex"], 622),
    ("can_ack_recovery", "run_can_recovery.py", ["can_recovery"], 701),
    ("can_winner", "run_can_winner.py", ["can_winner"], 811),
    ("can_resync", "run_can_resync.py", ["can_resync"], 819),
    ("can_fault_state", "run_can_fault_equal.py", ["can_fault_equal"], 1020),
    ("can_receive_flags", "run_can_rx_flags.py", ["can_rx_flags"], 1021),
    ("can_postflag", "run_can_postflag.py", ["can_postflag"], 1023),
    ("can_flag_bit_draft", "run_can_flag_bit.py", ["can_flag_bit"], 1076),
    ("can_flag_restart", "run_can_flag_restart.py", ["can_flag_restart"], 1024),
    ("can_tail_draft", "run_can_tail.py", ["can_tail"], 1067),
    ("usb", "run_usb_enum.py", ["usb_enum"], 1012),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit():
    results = {}
    for name, document, keys, xml_name in RECORDS:
        path = ROOT / "docs" / (document + ".json")
        evidence = json.loads(path.read_text())
        for key in keys:
            evidence = evidence[key]
        for filename, digest in evidence["source_sha256"].items():
            if sha(ROOT / filename) != digest:
                raise ValueError(f"{name}: source hash mismatch: {filename}")
        xml_path = ROOT / xml_name
        if sha(xml_path) != evidence["results_xml_sha256"]:
            raise ValueError(f"{name}: XML hash mismatch: {xml_name}")
        tree = ET.parse(xml_path).getroot()
        cases = tree.findall(".//testcase")
        passed = [c.attrib["name"] for c in cases if c.find("skipped") is None]
        expected_cases = [
            c["name"] if isinstance(c, dict) else c for c in evidence["cases"]
        ]
        if (
            tree.findall(".//failure")
            or tree.findall(".//error")
            or len(passed) != evidence["passed"]
            or len(cases) != len(passed)
            or sorted(passed) != sorted(expected_cases)
        ):
            raise ValueError(
                f"{name}: recorded test count/names do not match clean XML"
            )
        results[name] = {
            "evidence": str(path.relative_to(ROOT)),
            "command": evidence["command"],
            "passed": len(passed),
            "cases": passed,
            "verified_source_files": len(evidence["source_sha256"]),
            "source_sha256": evidence["source_sha256"],
            "results_xml": xml_name,
            "results_xml_sha256": sha(xml_path),
        }
    failures = {}
    for name, runner, arguments, words in CAPACITY:
        command = [
            sys.executable,
            str(ROOT / "study/protocol_exploration" / runner),
            *arguments,
        ]
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, check=False
        )
        expected = f"program contains {words} words; maximum is 128"
        if result.returncode != 1 or expected not in result.stderr:
            raise ValueError(
                f"{name}: unexpected capacity result: {result.returncode}: {result.stderr}"
            )
        failures[name] = {
            "command": "uv run --locked python study/protocol_exploration/"
            + runner
            + (" " + " ".join(arguments) if arguments else ""),
            "candidate_words": words,
            "production_limit_words": 128,
            "exit_code": result.returncode,
            "stderr": result.stderr.strip(),
        }
    physical = json.loads((ROOT / "docs/runtime_results.json").read_text())[
        "physical_source_sha256"
    ]
    for filename, digest in physical.items():
        if sha(ROOT / filename) != digest:
            raise ValueError(f"Physical baseline source changed: {filename}")
    return {
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "scope": "source_xml_integrity_and_reproduced_program_capacity_only",
        "full_protocol_acceptance_proven_by_this_tool": False,
        "full_goal_complete": False,
        "records": results,
        "capacity_failures": failures,
        "physical_source_sha256_unchanged": physical,
        "audit_tool_sha256": sha(Path(__file__)),
        "limitations": [
            "Requires matching saved XML/generated model artifacts; rerun experiments and refresh evidence records if missing",
            "Counts/hashes do not establish adequacy of protocol coverage",
            "Physical sources match historical results; no new physical flow or hardware proof",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit()
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"Verified {len(result['records'])} records spanning nine protocols and "
        f"reproduced {len(result['capacity_failures'])} production capacity failures. "
        "This is not full protocol acceptance."
    )


if __name__ == "__main__":
    main()
