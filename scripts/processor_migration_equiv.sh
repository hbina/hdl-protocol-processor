#!/usr/bin/env bash
# Prove the pure frontend processor matches the pre-migration transition function.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
baseline_revision=e4784a926d096a9fb3134eb3e1d08a6f6c4adaf1
out="$repo_dir/build/pure-baseline"
mkdir -p "$out"
baseline_dir="$(mktemp -d /tmp/bitlogic-baseline.XXXXXXXX)"
trap 'rm -rf -- "$baseline_dir"' EXIT
git archive "$baseline_revision" | tar -x -C "$baseline_dir"
CARGO_TARGET_DIR="$out/old-target" cargo run --locked --manifest-path "$baseline_dir/Cargo.toml" -p bitlogic --example protocol_processor -- verilog > "$out/processor.v"
artifacts=$(cargo run --locked -p bitlogic --example protocol_processor)
cp "$artifacts/processor_step.v" "$out/migrated.v"
# Compare the core modules; the clock/reset wrapper is unchanged. Hide generated
# internal names because node indices differ and are not correspondence points.
sed -n '1,/^endmodule/p' "$out/processor.v" | sed 's/^module processor_step(/module old_step(/' > "$out/equivalence.v"
sed -n '1,/^endmodule/p' "$out/migrated.v" | sed 's/^module processor_step(/module new_step(/' >> "$out/equivalence.v"
cat > "$out/equivalence.ys" <<'YOSYS'
read_verilog build/pure-baseline/equivalence.v
rename -hide old_step/w:n* new_step/w:n*
equiv_make old_step new_step migration_equiv
hierarchy -top migration_equiv
equiv_simple
equiv_status -assert
YOSYS
UV_CACHE_DIR="$repo_dir/build/uv-cache" uv run --locked yowasp-yosys -s "$out/equivalence.ys" -l "$out/equivalence.log"
