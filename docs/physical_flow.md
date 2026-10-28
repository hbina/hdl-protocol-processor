# Combinational CMOS5L physical flow

The active design is `tt_um_combhdl_demo`, sourced from `src/project.v` and
`src/combhdl_demo.v`. Tiny Tapeout metadata preserves the IHP CMOS5L 6×4 allocation
and sets `clock_hz: 0`. `CLOCK_PORT` is empty and `RUN_CTS` is zero; the wrapper's
unused `clk` pad is never a functional clock.

`src/pins.sdc` is supplied as `FALLBACK_SDC`, `PNR_SDC_FILE`, and
`SIGNOFF_SDC_FILE` so all relevant timing stages use the combinational contract.
It creates a portless 20 ns virtual clock and zero input/output delays. PDK
input driving cell/pin, output capacitance (fF converted to pF), maximum fanout,
optional maximum transition/capacitance, clock uncertainty/transition, and timing
derates are retained. There are no synchronizer exceptions, false paths, or
processor assertions. The constraints apply to all inputs, including unused
pads; there are no logic paths from the unused controls. The 20 ns period is a
proposed input-to-output budget, subject to the retained uncertainty/derates,
not achieved timing evidence. Actual OpenSTA/PDK validation requires the flow.

The Python tests exercise the SDC with Tcl command spies, both with and without
optional PDK limits. Tiny Tapeout `--create-user-config --ihp` succeeds and selects
the new sources, top, 6×4 DEF template, three corners, empty clock list, disabled
CTS, and custom SDC files. The physical launch was retried on 2026-10-28 and exits
with **`No compatible container engine found.`** Docker/Podman remains absent.
No new mapped netlist, extracted timing, ASIC area, DRC/LVS, or physical fit exists.

The root uv environment supplies compiler development and verification tools.
The existing `.asic-tools/venv` is a separate, legacy environment for the pinned
LibreLane/Tiny Tapeout physical toolchain, not a compiler requirement. It is used
here only for the physical tools already installed. No new physical dependencies
were installed. Versions:

| Tool | Pinned version |
|---|---|
| Tiny Tapeout support tools | `ihp-sg13cmos5l`, commit `d66cf179e7bc4d296362ab7e2e3b344dc3c4f665` |
| LibreLane | `3.1.0.dev3` |
| IHP Open PDK | `2bbec755dc67ca3db0261c3d6163e15735d66710` |
| Process | `ihp-sg13cmos5l` |

Once a compatible container engine is available, run from the repository root:

```sh
uv run --locked python -m tools.check_generated
uv run --no-project --python .asic-tools/venv/bin/python tt/tt_tool.py \
  --create-user-config --ihp
uv run --no-project --python .asic-tools/venv/bin/python -m librelane \
  --docker-no-tty --dockerized --pdk-root "$PWD/.asic-tools/pdk" \
  --pdk ihp-sg13cmos5l --manual-pdk --run-tag combhdl_demo \
  --force-run-dir runs/combhdl_demo src/config_merged.json
cp runs/combhdl_demo/final/nl/tt_um_combhdl_demo.nl.v test/gate_level_netlist.v
PDK_ROOT="$PWD/.asic-tools/pdk" uv run --locked make -B -C test GATES=yes
```

Mapped simulation uses the same 512 × 12 functional checks, compiling the PDK
UDP/cell models. The functional model shim inherited by the Makefile connects
DFF timing-model delayed inputs for Icarus; the new design must contain no DFFs.
Require new mapped evidence against the exact new source/netlist hashes. Never
use a processor netlist. Generic synthesis and simulation establish neither
physical timing nor process-specific cell behavior.

Require all-corner extracted setup/hold, slew/capacitance/fanout constraints,
6×4 fit, clean configured DRC/LVS, and exact source/netlist hashes and commands.
KLayout DRC/XOR are still disabled; equivalence, board validation, and realistic
activity-based power/IR analysis remain open. Historical fanout/signoff issues
belong to removed architectures and cannot be waived by new RTL tests. The old
[physical report](history/physical_flow.md) is preserved only as historical
results and installation/recovery notes; its processor build commands are obsolete.

The checked-in development-container recipe still targets the older `ihp-sg13g2`
process/tool versions. It is not a validated CMOS5L environment; use the pinned
physical environment above. Updating and rebuilding that recipe remains open.
