# SKY130 HD processor block study

Measured 2026-11-08. The selected target is a SKY130 HD standard-cell block,
using ORFS's `sky130hd` platform at TT, 25 °C and 1.80 V. It is an implementation
study of the processor core, not a pad-equipped chip or tapeout-ready design.
The pure structured-function processor was freshly synthesized, placed, routed,
extracted and regressed after migration. Earlier measurements remain preserved in
`evidence/2026-11-08/`; current measurements link to `evidence/pure-migration/`.

## Boundary and constraints

The [configuration](../asic/sky130hd/config.mk) selects 40% initial utilization,
0.55 placement density and a square core. The [SDC](../asic/sky130hd/constraints.sdc)
defines a 20 ns execution clock, 0.2 ns uncertainty, 0.1 ns clock/input transition,
5 ns maximum and 0.5 ns minimum input/output delays, and 0.01 pF output loads.
It asserts that all 41 non-clock input bits and all 122 state output bits are
present. No timing paths are declared false. An independent post-route
`check_setup -verbose` audit passes all checks, including unconstrained endpoints,
missing delays/clocks and combinational loops.

Program storage remains external combinational ROM, addressed by PC and stable
for execution. The I/O assumptions must accommodate its clock-to-data path; this
flow does not implement or time an external memory. Introducing synchronous
storage would change the processor/protocol cycle contract and is separate work.

Clock generation/distribution outside this block, input synchronizers/filters,
pad cells, level shifting and external electrical components remain the user's
top-module responsibilities. Core signals are 1.8 V logic; candidate 3.3 V board
interfaces require appropriate IO cells/level conversion. The route has no pad
ring, package, SRAM or external protocol devices. Constraints on logical pin
values/enables do not establish an electrical open-drain interface.

The chosen integration contract for a future wrapping top is a frozen 256×32
combinational instruction store outside this core, a supplied 50 MHz clock,
externally generated active-high reset sampled synchronously, and outputs masked
off until power/clock/reset are valid. Slow asynchronous GPIO inputs use two
synchronizing stages in that top; their latency must be included when selecting
protocol periods/holds. Source-synchronous return paths need a separately checked
round-trip sampling budget. Protocol test hold intervals are logical simulation values, not board rates.
For a 3.3 V board-facing implementation, select the
[SKY130 FD IO GPIO-v2 family](https://skywater-pdk.readthedocs.io/en/main/contents/libraries/sky130_fd_io/docs/user_guide.html)
around the 1.8 V core, with push-pull or output-enable-controlled drive-low/release
as appropriate. These are integration decisions, not implemented pad/CDC circuitry
or a qualified pad-ring configuration. Physical output-value/enable skew must
also be checked; logical atomic configuration does not guarantee electrical
simultaneity. None of these excluded blocks is counted in the area or timing.

## Reproduce

Install rootless Podman in addition to the Rust, Icarus and locked uv tools.
The container is pinned to this immutable Linux/amd64 image digest:

```text
docker.io/openroad/orfs@sha256:8b4f3942318d740ea1f73f4f895bbac150b32e41eb3b7baf7722adec6538bbcf
```

```sh
uv sync --locked
make processor-sky130-test
```

The [flow runner](../scripts/sky130_flow.sh) pulls the pinned image if needed,
then runs the container without network access. It mounts ASIC configuration
read-only and writes only `build/sky130hd/`. Podman storage is under `build/podman`;
its temporary runtime paths are overrideable through `BITLOGIC_PODMAN_ROOT`,
`BITLOGIC_PODMAN_RUNROOT` and `BITLOGIC_PODMAN_TMPDIR`. It preserves RTL timestamps
when contents match, allowing ORFS to reuse completed stages.

The image reports OpenROAD version `unknown` and Yosys `0.68+post` with commit
`UNKNOWN`; do not substitute an invented commit. The image digest identifies the
tool/platform contents. This uses the published
[OpenROAD flow](https://openroad-flow-scripts.readthedocs.io/en/latest/tutorials/FlowTutorial.html)
and [SKY130 HD platform](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/master/flow/platforms/sky130hd).

## Results

| Check | Observed result |
|---|---|
| RTL-to-layout flow | Technology synthesis, placement, clock tree, detailed routing, extraction and GDS emission complete |
| Non-filler standard-cell area | 15,713.8 µm²; 2,678 instances including physical overhead |
| Sequential cells | 122 |
| Core / die area | 35,914.4 / 37,550.7 µm² |
| Setup / hold worst slack | +10.3544 / +0.253807 ns at the specified 20 ns TT-corner target |
| Setup / hold TNS | Both zero |
| Slew / capacitance / fanout violations | Zero in final STA metrics |
| Detailed-router DRC / antenna-violating nets | Zero / zero after repair |
| Constraint sanity | All `check_setup` checks pass |
| Checkpoint comparison | Kepler reports no difference between technology-synthesis and final netlists |
| Routed-netlist functional regression | All 25 processor tests pass; clocked paths check 1,060,580 observations |

The routed functional simulation uses Liberty-derived behavioral cell models,
not SDF delays. Its combinational-only test still exercises source RTL; the
clocked tests instantiate the actual `6_final.v`. This complements extracted
static timing rather than replacing it. The checkpoint comparison is scoped to
mapped implementation netlists, not a proof of native Rust/IR/frontend semantics.

The [summary](evidence/pure-migration/sky130_summary.json) records artifact hashes and
scoped metrics. Raw [finish metrics](evidence/pure-migration/sky130_finish_metrics.json),
[routing metrics](evidence/pure-migration/sky130_route_metrics.json),
[timing report](evidence/pure-migration/sky130_finish.rpt),
[constraint audit](evidence/pure-migration/sky130_constraint_audit.log) and
[checkpoint log](evidence/pure-migration/sky130_checkpoint_lec.log) preserve local evidence.
The upstream finish JSON repeats some generic area keys; the table uses the
explicit `area__stdcell`, core-area and die-area keys. Re-run the
[report checker](../scripts/sky130_report.py) after reproducing the flow.

GDS, DEF, extracted SPEF, database and routed Verilog are generated under
`build/sky130hd/orfs/results/sky130hd/bitlogic_processor/base/` and are not checked
in. The summary hashes identify the measured versions. The generic logic mapping
is a separate [baseline](processor_synthesis.md), with different cell counts.

## Remaining signoff limitations

This single TT/RC study does not establish multi-corner timing closure, silicon
frequency, IO/ROM/system timing, CDC safety, foundry-deck DRC, LVS, package
integration or manufactured hardware behavior. Detailed-router DRC zero is not
foundry signoff. No FPGA or board execution is claimed.

OpenROAD warns that a physical decap master has signal pins without a Liberty
cell. Kepler warns about unsupported clock-gating library models; none of those
cells occur in this netlist. These warnings are retained as limits, not hidden.
The flow's 0.742931 mW power estimate uses default/vectorless activity; it is not
a protocol-activity power measurement or IR/EM signoff. Chip-level IO and power
integration, full corners and independent physical verification remain future
milestones beyond this scoped block study.
