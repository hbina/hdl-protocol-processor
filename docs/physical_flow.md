# Combinational CMOS5L physical flow

The active design is `tt_um_combhdl_demo`, sourced from `src/project.v` and
`src/combhdl_demo.v`. Tiny Tapeout metadata preserves the IHP CMOS5L 6×4 allocation
and sets `clock_hz: 0`. `CLOCK_PORT` is empty and `RUN_CTS` is false. The wrapper's
unused `clk` pad is never a functional clock.

Rootless Podman **4.9.3** is installed and working. The corrected flow at
`runs/combhdl_demo_02` completed on **2026-10-29** and passes the provenance-aware
physical audit. Its exact routed netlist passes all 512 meaningful inputs × 12
unused-control patterns = **6,144 mapped observations**.

The design fits the 6×4 DEF allocation: **53 non-filler standard cells**,
**627.782 µm²** standard-cell area, **0.06957%** utilization. Routing DRC,
Magic DRC, and LVS report **0 / 0 / 0** errors. There are no flip-flops, latches,
memories, or physical clock buffers. All corners have zero setup/hold, slew,
capacitance, and fanout violations. Source/artifact hashes, exact commands, image
digests, tool versions, report hashes, and metrics are in
[physical_results.json](physical_results.json).

| PVT corner | Worst setup slack (ns) | Worst hold slack (ns) |
|---|---:|---:|
| nom_slow_1p08V_125C | +17.431774 | +0.670131 |
| nom_typ_1p20V_25C | +18.301123 | +0.326408 |
| nom_fast_1p32V_m40C | +18.776247 | +0.139100 |

## Timing contract and corrections from real OpenSTA reports

`src/pins.sdc` is supplied as `FALLBACK_SDC`, `PNR_SDC_FILE`, and
`SIGNOFF_SDC_FILE`. It creates one portless **20 ns virtual clock** and constrains
all input/output ports with **zero external delays**. PDK input driving cell/pin,
output capacitance (fF converted to pF), maximum fanout, applicable transition and
capacitance limits, **0.25 ns clock uncertainty**, and **5% early/late timing
derates** are retained. No synchronizer exceptions, false paths, or processor
assertions remain. There are no functional paths from unused board controls.

Real OpenSTA reports exposed two clock assumptions in the initial SDC. A virtual
clock cannot have a physical transition or propagated network. The SDC now
explicitly uses `unset_propagated_clock` and supplies no virtual-clock transition.
Actual corner reports must show exactly `comb_reference`, no sources, `Virtual:
yes`, `Propagated: no`, and period 20 ns. They must contain constrained input-to-
output paths for all eight `uo_out` bits, with no functional clock or storage.

The PDK defaults enforce setup only at the typical corner and disable slew/cap
acceptance gates. The project now explicitly sets `TIMING_VIOLATION_CORNERS`,
`SETUP_VIOLATION_CORNERS`, `HOLD_VIOLATION_CORNERS`,
`MAX_SLEW_VIOLATION_CORNERS`, and `MAX_CAP_VIOLATION_CORNERS` to `["*"]`.
`tools.report_physical` also requires zero fanout violations and complete
parasitic annotation of connected logic at every corner.

The physical tools insert combinational delay cells to satisfy the retained
hold uncertainty and margins. These are not registers. Storage checks inspect
actual Liberty `ff`/`latch` definitions; the `dlygate` prefix alone does not imply
state. Extracted setup/hold checks establish compliance with this I/O contract,
not a functional clock frequency or guaranteed board behavior.

## Run and reproduce

The root uv environment supplies all Python tools: compiler development,
verification, LibreLane, and Tiny Tapeout orchestration. Their dependencies are
declared in `pyproject.toml` and pinned in `uv.lock`. Install them with
`uv sync --locked`; run them with `uv run --locked`. The former separate physical
virtual environment has been deleted. The container still supplies compatible
native synthesis, routing, and layout-checking binaries.

The recorded completed run retains its original interpreter path as historical
provenance. Current launch commands below use only the repository's `.venv`.
After deleting the former environment, root-uv configuration generation produces
the same merged configuration as the recorded routed run. A root-uv container
smoke run at `runs/combhdl_root_uv_smoke` passes synthesis and pre-placement STA
at all three corners. This validates the environment migration without claiming
a second routed signoff run; details are in [verification.json](verification.json).

| Tool | Pinned version |
|---|---|
| Container | `ghcr.io/librelane/librelane:3.1.0.dev3` (resolved image digest recorded per run) |
| Tiny Tapeout support tools | `ihp-sg13cmos5l`, `d66cf179e7bc4d296362ab7e2e3b344dc3c4f665` |
| LibreLane | `3.1.0.dev3` |
| Native Yosys | `0.66`, `86f2ddebce7e98ce7cacc27e8a5c14cb53b51b51` |
| OpenROAD | `dcf36133a369abc8f3c5e5738cd4d82e4903c0e0` |
| Magic | `8.3.674` |
| Netgen | `1.5.320` |
| IHP Open PDK | `2bbec755dc67ca3db0261c3d6163e15735d66710` |
| Process | `ihp-sg13cmos5l` |

Use the installed Podman engine; Docker is also supported. A fresh run directory
is required so previous reports cannot be silently overwritten:

```sh
uv run --locked python -m tools.check_generated
uv run --locked python -m tools.run_physical \
  --engine podman --run-dir runs/combhdl_demo_next
uv run --locked python -m tools.check_mapped --run-dir runs/combhdl_demo_next
uv run --locked python -m tools.report_physical --run-dir runs/combhdl_demo_next
```

The launcher creates the empty run directory required by LibreLane, regenerates
Tiny Tapeout's merged configuration, and records source snapshots, hashes,
repository revisions, engine/tool versions, command, image digest, return code,
and output hashes under `build/physical/<run-name>/`. Its `console.log` and the
run's `flow.log` show progress. The launcher refuses an existing run/provenance
directory and rejects sources changed during a run.

Mapped simulation selects that run's exact final netlist using `GATE_NETLIST`;
it does not copy an arbitrary file into a shared location. It uses Icarus, the
pinned PDK UDP/cell models, and the unchanged exhaustive board test. The legacy
functional-model shim remains for Icarus timing-check compatibility; actual
routed cells are checked to contain no storage. The simulator settles before
checking, with no claim of physical delay or glitch freedom.

The final audit requires completed run provenance, current source hashes, exact
mapped-netlist hash, all-corner finite positive timing slack, zero timing/electrical
violations, correctly constrained output paths and saved I/O delays, actual DEF
bounds matching 6×4, no storage, and passing routed DRC, Magic DRC, LVS, and mapped
regression. It writes `docs/physical_results.json` only after all these checks pass.
The old [physical report](history/physical_flow.md) is historical; its processor
commands and results are not current evidence.

## Remaining limits

KLayout DRC and Magic/KLayout XOR are still disabled. Formal equivalence, board
validation, and realistic activity-based power/IR analysis remain open; default
power assumptions and missing explicit voltage-source locations are not signoff.
The development-container recipe still targets an older PDK/toolchain and is not
a validated CMOS5L replacement.

Two pinned LibreLane resizer/routing scripts internally attempt to propagate
all clocks, producing `STA-0450` warnings for the virtual clock even with the
correct SDC. The clock remains ideal/virtual in actual extracted reports. The
flow also reports unsupported LEF58 CUTCLASS metadata and ignores unused power
pins from the template. These tool/PDK warnings are retained in the evidence,
not converted into claims that skipped checks passed. The ten unused input pads
have no gate/antenna or connected-parasitic paths; meaningful input/output paths
and critical connectivity are checked separately.
