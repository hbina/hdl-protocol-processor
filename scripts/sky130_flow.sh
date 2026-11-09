#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
image='docker.io/openroad/orfs@sha256:8b4f3942318d740ea1f73f4f895bbac150b32e41eb3b7baf7722adec6538bbcf'
out="$repo_dir/build/sky130hd"
runtime="${BITLOGIC_PODMAN_TMPDIR:-/tmp/bitlogic-podman-runtime/libpod-tmp}"
mkdir -p "$out" "$runtime"
podman_cmd=(podman --root "${BITLOGIC_PODMAN_ROOT:-$repo_dir/build/podman}"
    --runroot "${BITLOGIC_PODMAN_RUNROOT:-/tmp/bitlogic-podman-run}" --tmpdir "$runtime")
if ! "${podman_cmd[@]}" image exists "$image"; then
    "${podman_cmd[@]}" pull "$image"
fi
container=("${podman_cmd[@]}" run --rm --cgroups=disabled --network=none
    -v "$repo_dir/asic:/work/asic:ro" -v "$out:/work/build:rw" "$image")

case "${1:-run}" in
    run)
        artifacts=$(cargo run --locked -p bitlogic --example protocol_processor)
        cp "$artifacts/implementation.v" "$out/emitted_candidate.v"
        if ! cmp -s "$out/emitted_candidate.v" "$out/protocol_processor.v"; then
            cp "$out/emitted_candidate.v" "$out/protocol_processor.v"
        fi
        "${container[@]}" bash -lc 'set -e; source /OpenROAD-flow-scripts/env.sh; openroad -version; yosys -V; make -C /OpenROAD-flow-scripts/flow DESIGN_CONFIG=/work/asic/sky130hd/config.mk WORK_HOME=/work/build/orfs NUM_CORES=4' | tee "$out/run.log"
        ;;
    models)
        "${container[@]}" /OpenROAD-flow-scripts/tools/install/yosys/bin/yosys -Q -p 'read_liberty -ignore_miss_func /OpenROAD-flow-scripts/flow/platforms/sky130hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib; write_verilog -noattr /work/build/sky130hd_cells.v' > "$out/cell_models.log"
        ;;
    audit)
        "${container[@]}" /OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad -exit /work/asic/sky130hd/audit.tcl | tee "$out/constraint_audit.log"
        ;;
    *) echo 'usage: sky130_flow.sh [run|models|audit]' >&2; exit 2 ;;
esac
