#!/usr/bin/env python3
"""Paired unmapped core synthesis; no PDK area/timing/signoff claim."""

import argparse
import hashlib
import json
import os
import subprocess

from generic_frontier import ROOT, expanded_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yosys", default=str(ROOT / ".asic-tools/venv/bin/yowasp-yosys")
    )
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    build = ROOT / "test/sim_build/frontier_synth"
    build.mkdir(parents=True, exist_ok=True)
    model = ROOT / "test/sim_build/can_duplex_frontier1024/protocol_core_frontier1024.v"
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_text(expanded_source())
    summaries = {}
    for name, source in [
        ("baseline", ROOT / "src/protocol_core.v"),
        ("frontier", model),
    ]:
        relative = source.relative_to(ROOT)
        script = build / f"{name}.ys"
        script.write_text(
            f"read_verilog {relative}\nsynth -top protocol_core -noabc\n"
            f"tee -o {build.relative_to(ROOT)}/{name}_stats.json stat -json\n"
        )
        if args.prepare_only:
            continue
        command = [
            args.yosys,
            "-Q",
            "-T",
            "-q",
            "-l",
            str(build / f"{name}.log"),
            "-s",
            str(script),
        ]
        subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            env=dict(
                os.environ,
                YOWASP_CACHE_DIR=os.environ.get(
                    "YOWASP_CACHE_DIR", "/tmp/asic-yowasp-cache"
                ),
            ),
        )
        stats_path = build / f"{name}_stats.json"
        stats = json.loads(stats_path.read_text())
        module = stats["modules"]["\\protocol_core"]
        summaries[name] = {
            "source": str(relative),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "command": command,
            "creator": stats["creator"],
            "generic_cells": module["num_cells"],
            "cells_by_type": module["num_cells_by_type"],
            "stats_sha256": hashlib.sha256(stats_path.read_bytes()).hexdigest(),
        }
    if not args.prepare_only:
        (build / "evidence.json").write_text(
            json.dumps(
                {
                    "scope": "unmapped_core_only_noabc",
                    "technology_area_or_timing_verified": False,
                    "variants": summaries,
                },
                indent=2,
            )
            + "\n"
        )
        print(
            json.dumps(
                {name: value["generic_cells"] for name, value in summaries.items()}
            )
        )


if __name__ == "__main__":
    main()
