"""Audit and record a completed CMOS5L run and its exhaustive mapped regression."""

import argparse
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any

from .run_physical import ROOT, sha256, source_hashes


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def audit(run_dir: Path) -> dict[str, Any]:
    provenance = ROOT / "build/physical" / run_dir.name
    launch = json.loads((provenance / "launch.json").read_text())
    require(
        launch["status"] == "finished" and launch["returncode"] == 0,
        "physical flow has not passed",
    )
    require(launch["run_dir"] == str(run_dir), "run path disagrees with provenance")
    require(
        launch["sources_unchanged"] and launch["source_sha256"] == source_hashes(),
        "physical sources are stale",
    )
    config = json.loads((run_dir / "resolved.json").read_text())
    require(config["DESIGN_NAME"] == "tt_um_combhdl_demo", "wrong physical top")
    require(
        not config["CLOCK_PORT"] and not config["RUN_CTS"],
        "functional clock/CTS must be disabled",
    )
    require(config["CLOCK_PERIOD"] == 20, "wrong timing period")
    require(
        config["DIE_AREA"] == [0, 0, 1289.28, 710.64],
        "die does not match the CMOS5L 6x4 template",
    )
    require(
        set(config["PNR_CORNERS"])
        == {"nom_fast_1p32V_m40C", "nom_slow_1p08V_125C", "nom_typ_1p20V_25C"},
        "all three expected PVT corners are required",
    )
    for kind in ("SETUP", "HOLD", "MAX_SLEW", "MAX_CAP"):
        require(
            config[f"{kind}_VIOLATION_CORNERS"] == ["*"],
            f"{kind} acceptance must cover all corners",
        )
    metrics_path = run_dir / "final/metrics.json"
    metrics = json.loads(metrics_path.read_text())
    for key in (
        "route__drc_errors",
        "magic__drc_error__count",
        "design__lvs_error__count",
        "design__critical_disconnected_pin__count",
        "synthesis__check_error__count",
        "design__inferred_latch__count",
    ):
        require(metrics.get(key) == 0, f"missing or nonzero metric: {key}")
    require(
        0 < metrics["design__instance__utilization"] < 1,
        "design does not fit or utilization is invalid",
    )
    final_def = run_dir / "final/def/tt_um_combhdl_demo.def"
    def_text = final_def.read_text()
    units = re.search(r"UNITS DISTANCE MICRONS (\d+) ;", def_text)
    bounds = re.search(r"DIEAREA \( (\d+) (\d+) \) \( (\d+) (\d+) \) ;", def_text)
    require(units is not None and bounds is not None, "missing physical DEF dimensions")
    assert units is not None and bounds is not None
    actual_area = [int(coordinate) / int(units[1]) for coordinate in bounds.groups()]
    require(
        actual_area == config["DIE_AREA"],
        "routed DEF does not match the 6x4 allocation",
    )
    saved_sdc = (run_dir / "final/sdc/tt_um_combhdl_demo.sdc").read_text()
    for direction, ports in (
        (
            "input",
            {"clk", "ena", "rst_n"}
            | {f"{bus}[{bit}]" for bus in ("ui_in", "uio_in") for bit in range(8)},
        ),
        (
            "output",
            {
                f"{bus}[{bit}]"
                for bus in ("uo_out", "uio_out", "uio_oe")
                for bit in range(8)
            },
        ),
    ):
        delays = re.findall(
            rf"^set_{direction}_delay (\S+).*\[get_ports \{{([^}}]+)\}}\]",
            saved_sdc,
            re.MULTILINE,
        )
        require(
            {port for _, port in delays} == ports
            and all(float(value) == 0 for value, _ in delays),
            f"saved SDC does not constrain all {direction} ports with zero delay",
        )
    sta_dirs = list(run_dir.glob("*-openroad-stapostpnr"))
    require(len(sta_dirs) == 1, "expected exactly one final extracted timing stage")
    sta = sta_dirs[0]
    corners: dict[str, Any] = {}
    outputs = {f"uo_out[{bit}]" for bit in range(8)}
    for corner in config["PNR_CORNERS"]:
        reports = {
            name: sta / corner / name
            for name in ("clock.rpt", "min.rpt", "max.rpt", "checks.rpt")
        }
        clock = reports["clock.rpt"].read_text()
        require(
            re.findall(r"^Clock: (.+)$", clock, re.MULTILINE) == ["comb_reference"],
            "expected exactly the virtual reference clock",
        )
        require(
            "Sources: \n" in clock
            and "Virtual: yes" in clock
            and "Propagated: no" in clock
            and "Period: 20.000000" in clock,
            "reference must be ideal, virtual, portless, 20 ns",
        )
        endpoint_counts: dict[str, int] = {}
        for name in ("min.rpt", "max.rpt"):
            text = reports[name].read_text()
            endpoints = re.findall(
                r"^Endpoint: (\S+) \(output port clocked by comb_reference\)$",
                text,
                re.MULTILINE,
            )
            require(
                set(endpoints) == outputs,
                f"{corner}/{name}: all eight output bits must be timed",
            )
            require(
                set(re.findall(r"^Path Group: (.+)$", text, re.MULTILINE))
                == {"comb_reference"},
                "unexpected unconstrained or functional-clock path group",
            )
            starts = re.findall(
                r"^Startpoint: (\S+) \(input port clocked by comb_reference\)$",
                text,
                re.MULTILINE,
            )
            require(
                len(starts) == len(endpoints)
                and all(
                    re.fullmatch(r"ui_in\[[0-7]\]|uio_in\[0\]", name) for name in starts
                ),
                "paths must start at meaningful input ports",
            )
            delays = re.findall(
                r"([-+]?\d+\.\d+)\s+[-+]?\d+\.\d+\s+[\^v]?\s*(input|output) external delay",
                text,
            )
            require(
                len(delays) == 2 * len(endpoints)
                and all(float(value) == 0 for value, _ in delays),
                "every timed path must have zero input and output external delays",
            )
            require(
                sum(kind == "input" for _, kind in delays) == len(endpoints),
                "missing input delay evidence",
            )
            endpoint_counts[name] = len(endpoints)
        corner_metrics = {
            name: metrics.get(f"{name}__corner:{corner}")
            for name in (
                "timing__setup__ws",
                "timing__hold__ws",
                "timing__setup__tns",
                "timing__hold__tns",
                "timing__setup_vio__count",
                "timing__hold_vio__count",
                "design__max_slew_violation__count",
                "design__max_cap_violation__count",
                "design__max_fanout_violation__count",
                "timing__unannotated_net_filtered__count",
            )
        }
        for name, value in corner_metrics.items():
            require(
                isinstance(value, (int, float)) and math.isfinite(value),
                f"{corner}: missing or nonfinite {name}",
            )
            require(
                value > 0 if name.endswith("__ws") else value == 0,
                f"{corner}: failing {name}={value}",
            )
        corners[corner] = {
            "metrics": corner_metrics,
            "timed_output_paths": endpoint_counts,
            "report_sha256": {name: sha256(path) for name, path in reports.items()},
        }
        require(
            "Warning:" not in reports["checks.rpt"].read_text(),
            f"{corner}: STA setup/constraint warnings remain",
        )
    synth_dirs = list(run_dir.glob("*-yosys-synthesis"))
    require(len(synth_dirs) == 1, "missing synthesis evidence")
    stat = json.loads((synth_dirs[0] / "reports/stat.json").read_text())
    module = stat["modules"]["\\tt_um_combhdl_demo"]
    require(
        module["num_memories"] == 0
        and module["num_processes"] == 0
        and module["sequential_area"] == 0,
        "synthesized storage detected",
    )
    netlist = run_dir / "final/nl/tt_um_combhdl_demo.nl.v"
    require(
        sha256(netlist) == launch["artifact_sha256"][str(netlist.relative_to(run_dir))],
        "final netlist changed",
    )
    liberty = (
        ROOT
        / ".asic-tools/pdk/ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/lib/sg13cmos5l_stdcell_typ_1p20V_25C.lib"
    )
    cells = re.split(r"(?m)^  cell\s*\(", liberty.read_text())[1:]
    sequential = {
        cell.split(")", 1)[0].strip().strip('"')
        for cell in cells
        if re.search(r"\b(?:ff|latch|ff_bank|latch_bank|memory)\s*\(", cell)
    }
    instantiated = set(
        re.findall(
            r"^\s*(sg13cmos5l_\w+)\s+\S+\s*\(", netlist.read_text(), re.MULTILINE
        )
    )
    require(
        bool(sequential) and bool(instantiated),
        "missing Liberty or netlist cell evidence",
    )
    require(not (instantiated & sequential), "storage in routed netlist")
    mapped = json.loads((provenance / "mapped_simulation.json").read_text())
    require(
        mapped["result"] == "passed"
        and mapped["netlist_sha256"] == sha256(netlist)
        and mapped["source_sha256"] == source_hashes(),
        "mapped simulation does not match current routed sources",
    )
    require(mapped["observations"] == 6144, "mapped functional coverage is incomplete")
    for relative, digest in launch["artifact_sha256"].items():
        require(
            sha256(run_dir / relative) == digest,
            f"physical artifact changed: {relative}",
        )
    require((run_dir / "final/gds/tt_um_combhdl_demo.gds").is_file(), "no GDS output")
    engine = "podman" if "host" in launch["engine"] else "docker"
    versions_command = [
        engine,
        "run",
        "--rm",
        "--pull=never",
        launch["container_inspect"][0]["Id"],
        "python3",
        "-c",
        "import json,subprocess; commands={'yosys':['yosys','-V'],'openroad':['openroad','-version'],'magic':['magic','--version']}; print(json.dumps({name:subprocess.check_output(command,text=True).strip() for name,command in commands.items()}))",
    ]
    tool_versions = json.loads(
        subprocess.run(
            versions_command, check=True, capture_output=True, text=True
        ).stdout
    )
    lvs_logs = list(run_dir.glob("*-netgen-lvs/netgen-lvs.log"))
    require(len(lvs_logs) == 1, "missing Netgen tool evidence")
    tool_versions["netgen"] = next(
        line
        for line in lvs_logs[0].read_text().splitlines()
        if line.startswith("Netgen ")
    )
    return {
        "design": "tt_um_combhdl_demo",
        "run_dir": str(run_dir),
        "flow_result": "passed",
        "source_sha256": source_hashes(),
        "launch_command": launch["command"],
        "configuration_command": launch["configuration_command"],
        "git_revision_at_launch": launch["git_revision"],
        "pdk_revision": launch["pdk_revision"],
        "tt_revision": launch["tt_revision"],
        "container_image": launch["container_image"],
        "container_id": launch["container_inspect"][0]["Id"],
        "container_repo_digests": launch["container_inspect"][0]["RepoDigests"],
        "physical_versions": launch["physical_versions"],
        "tool_versions": tool_versions,
        "tool_versions_command": versions_command,
        "liberty_sha256": sha256(liberty),
        "engine_version": launch["engine"]["version"],
        "artifact_sha256": launch["artifact_sha256"],
        "metrics_sha256": sha256(metrics_path),
        "allocation": {"tiles": "6x4", "die_area_um": config["DIE_AREA"]},
        "actual_def_die_area_um": actual_area,
        "all_corner_timing": corners,
        "synthesis_statistics": module,
        "final_metrics": metrics,
        "mapped_simulation": mapped,
        "flow_warnings": (run_dir / "warning.log").read_text().splitlines(),
        "limitations": [
            "KLayout DRC and Magic/KLayout XOR disabled",
            "No formal equivalence or board validation",
            "Power/IR uses default activity and lacks explicit voltage-source locations",
            "Older development-container recipe is not validated for CMOS5L",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/physical_results.json"
    )
    args = parser.parse_args()
    try:
        result = audit(args.run_dir.resolve())
    except (ValueError, KeyError, FileNotFoundError) as error:
        parser.exit(1, f"physical audit: {error}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Physical and mapped verification PASS; recorded {args.output}")


if __name__ == "__main__":
    main()
