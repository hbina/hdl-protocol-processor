"""Check and summarize the scoped SKY130 block implementation evidence."""

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/sky130hd"
FLOW = BUILD / "orfs"
STAGE = Path("sky130hd/bitlogic_processor/base")
IMAGE = (
    "docker.io/openroad/orfs@sha256:"
    "8b4f3942318d740ea1f73f4f895bbac150b32e41eb3b7baf7722adec6538bbcf"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def metrics(filename: str) -> dict:
    # ORFS repeats some generic keys. We use explicit stdcell/core-area keys;
    # repeated routing iteration metrics intentionally retain their final value.
    return json.loads((FLOW / "logs" / STAGE / filename).read_text())


def collect() -> dict:
    finish = metrics("6_report.json")
    route = metrics("5_2_route.json")
    for key in (
        "finish__timing__setup__tns",
        "finish__timing__hold__tns",
        "finish__timing__drv__setup_violation_count",
        "finish__timing__drv__hold_violation_count",
        "finish__timing__drv__max_slew",
        "finish__timing__drv__max_cap",
        "finish__timing__drv__max_fanout",
        "finish__flow__errors__count",
    ):
        require(finish[key] == 0, f"nonzero final violation metric: {key}")
    for key in ("finish__timing__setup__ws", "finish__timing__hold__ws"):
        require(
            math.isfinite(finish[key]) and finish[key] >= 0,
            f"negative/nonfinite final slack: {key}",
        )
    for key in (
        "detailedroute__route__drc_errors",
        "detailedroute__antenna__violating__nets",
        "detailedroute__antenna__violating__pins",
        "detailedroute__flow__errors__count",
    ):
        require(route[key] == 0, f"nonzero final routing metric: {key}")

    audit = (BUILD / "constraint_audit.log").read_text()
    audit_body = audit.split("BEGIN_CONSTRAINT_AUDIT\n", 1)[1].split(
        "END_CONSTRAINT_AUDIT", 1
    )[0]
    require(audit_body.strip() == "CHECK_SETUP_RESULT=1", "constraint audit failed")
    lec = (FLOW / "logs" / STAGE / "6_final_lec.log").read_text()
    require("1_synth_lec.v" in lec and "6_final_lec.v" in lec, "wrong LEC inputs")
    require("No difference was found." in lec, "checkpoint comparison failed")

    result = FLOW / "results" / STAGE
    netlist = (result / "6_final.v").read_text()
    require("__dlclkp_" not in netlist, "unsupported clock-gating model is used")
    require("__sdlclkp_" not in netlist, "unsupported clock-gating model is used")
    test_log = BUILD / "postroute_tests.log"
    tests = test_log.read_text()
    require("test result: ok. 25 passed; 0 failed;" in tests, "incomplete regression")
    require(
        test_log.stat().st_mtime >= (result / "6_final.v").stat().st_mtime,
        "regression predates the routed netlist",
    )
    edges = sum(int(n) for n in re.findall(r"(\d+) clocked HDL edges", tests))
    require(edges == 1_060_580, "clocked regression coverage changed")

    inputs = [
        BUILD / "protocol_processor.v",
        ROOT / "asic/sky130hd/config.mk",
        ROOT / "asic/sky130hd/constraints.sdc",
        ROOT / "asic/sky130hd/audit.tcl",
        ROOT / "scripts/sky130_flow.sh",
        ROOT / "scripts/sky130_report.py",
        FLOW / "logs" / STAGE / "6_report.json",
        FLOW / "logs" / STAGE / "5_2_route.json",
        FLOW / "logs" / STAGE / "6_final_lec.log",
        BUILD / "constraint_audit.log",
        result / "6_final.v",
        result / "6_final.gds",
        result / "6_final.spef",
        BUILD / "sky130hd_cells.v",
        test_log,
    ]
    hashes = {}
    for path in inputs:
        data = path.read_bytes()
        require(bool(data), f"empty artifact: {path}")
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(data).hexdigest()

    return {
        "date_utc": datetime.now(UTC).date().isoformat(),
        "scope": "processor block; external ROM, synchronizers, pads and chip signoff excluded",
        "image": IMAGE,
        "platform": "sky130hd",
        "corner": "TT, 25 C, 1.80 V; extracted interconnect",
        "clock_period_ns": 20.0,
        "tool_version_note": "image reports OpenROAD unknown and Yosys 0.68+post UNKNOWN; digest pins binaries",
        "stdcell_area_um2": finish["finish__design__instance__area__stdcell"],
        "stdcell_count_excluding_fill": finish[
            "finish__design__instance__count__stdcell"
        ],
        "core_area_um2": finish["finish__design__core__area"],
        "die_area_um2": finish["finish__design__die__area"],
        "sequential_cells": finish[
            "finish__design__instance__count__class:sequential_cell"
        ],
        "setup_worst_slack_ns": finish["finish__timing__setup__ws"],
        "hold_worst_slack_ns": finish["finish__timing__hold__ws"],
        "routing_drc_errors": route["detailedroute__route__drc_errors"],
        "antenna_violating_nets": route["detailedroute__antenna__violating__nets"],
        "constraint_sanity": "passed all check_setup checks",
        "checkpoint_comparison": "Kepler final netlist vs technology synthesis: no difference",
        "postroute_tests": 25,
        "clocked_hdl_edges": edges,
        "simulation": "Liberty-derived functional cell models; no SDF; combinational test remains source RTL",
        "vectorless_power_estimate_w": finish["finish__power__total"],
        "power_limit": "default activity, not protocol-activity power or IR/EM signoff",
        "sha256": hashes,
    }


if __name__ == "__main__":
    report = collect()
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    (BUILD / "summary.json").write_text(text)
    print(text, end="")
