> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# Pin-v1 physical implementation

The new design uses the same pinned CMOS5L toolchain, 6×4 allocation, 20 ns
clock target, and three corners as the historical flow below. The active source
list contains only project.v and protocol_core.v. The active timing file is
src/pins.sdc: it cuts only paths from asynchronous inputs to the 15 first-stage
synchronizer D pins and checks that all 15 are found. Stage-to-stage timing and
board-clocked configuration paths remain constrained.

Current blocker: LibreLane 3.1.0.dev3 and the pinned PDK are installed, but
Docker/Podman is absent. The new-design flow exits with
`No compatible container engine found.` No new physical results or mapped-test
passes exist. Historical runs below describe the removed runtime design.

After restoring the documented container environment:

```sh
uv run --no-project --python .asic-tools/venv/bin/python tt/tt_tool.py --create-user-config --ihp
uv run --no-project --python .asic-tools/venv/bin/python -m librelane \
  --docker-no-tty --dockerized --pdk-root "$PWD/.asic-tools/pdk" \
  --pdk ihp-sg13cmos5l --manual-pdk --run-tag pin_direct \
  --force-run-dir runs/pin_direct src/config_merged.json
cp runs/pin_direct/final/nl/tt_um_protocol_emulator.nl.v test/gate_level_netlist.v
PDK_ROOT="$PWD/.asic-tools/pdk" uv run --locked make -B -C test GATES=yes
```

Require all six new pin-only wrapper tests against that exact netlist, positive
setup/hold timing in all configured corners, clean configured DRC/LVS checks,
and fit in the 6×4 allocation. Do not reuse an old gate_level_netlist.v.
Do not reduce the 256-word target to conceal a fit failure. Record area,
utilization, timing, exact commands, and source/netlist hashes with new evidence.
The input synchronizer constraints still require validation in the mapped flow;
RTL checks cannot establish CDC/MTBF signoff.

## Historical physical flow and results

# Local CMOS5L physical-design flow

This project uses the Tiny Tapeout IHP CMOS5L flow to turn the Verilog RTL
into a placed-and-routed GDS layout. The toolchain is installed locally under
the project directory; it does not modify the system Python installation.

## Pinned toolchain

Keep local and CI runs on these versions unless the
`TinyTapeout/tt-gds-action` `ihp-cmos5l` branch is deliberately updated:

| Component | Version |
|---|---|
| Tiny Tapeout support tools | `ihp-sg13cmos5l` branch; installed commit `d66cf179e7bc4d296362ab7e2e3b344dc3c4f665` |
| LibreLane | `3.1.0.dev3` |
| IHP Open PDK | commit `2bbec755dc67ca3db0261c3d6163e15735d66710` |
| LibreLane PDK name | `ihp-sg13cmos5l` |

The project sets `OPENROAD_THREADS=8` explicitly. In the pinned version, an
omitted thread count is stringified as `None`, which OpenROAD rejects; the
explicit setting prevents that slow fallback. Runtime builds also supply
`src/runtime.sdc` for PnR and signoff, with a selective request-synchronizer
exception and conservative held-data timing.
`PNR_CORNERS` explicitly enables fast, slow, and typical CMOS5L corners during
physical optimization; the pinned tool defaults to the typical corner alone
when this setting is omitted.
Intermediate STA uses only the first corner returned by the tool (fast in this
pinned installation), regardless of the configured list order. Acceptance uses
final extracted reports for every separate corner; an intermediate scalar slack
must not be treated as an all-corner result.

The local files have this layout:

```text
.asic-tools/
  venv/                 LibreLane and Python dependencies
  uv-cache/             local uv package cache
  pdk/                  pinned IHP Open PDK checkout
tt/                     Tiny Tapeout support tools
runs/                   generated hardening runs
```

All four paths are generated or downloaded and are excluded from version
control. Docker is the only system-level prerequisite. The hardening flow uses
Docker for the implementation tools, so separate system installations of
Yosys, OpenROAD, Magic, or Netgen are not required.

## Activate an existing installation

Run these commands from the repository root in each new shell:

```sh
export ASIC_TOOL_ROOT="$PWD/.asic-tools"
export UV_CACHE_DIR="$ASIC_TOOL_ROOT/uv-cache"
export PDK_ROOT="$ASIC_TOOL_ROOT/pdk"
export PDK=ihp-sg13cmos5l
export LIBRELANE_VERSION=3.1.0.dev3
source "$ASIC_TOOL_ROOT/venv/bin/activate"
```

Verify the installation before hardening:

```sh
python -c 'from importlib.metadata import version; print(version("librelane"))'
git -C tt branch --show-current
git -C "$PDK_ROOT" rev-parse HEAD
docker info
```

The expected values are `3.1.0.dev3`, `ihp-sg13cmos5l`, and the PDK commit
listed above.

## Recreate the installation

The following is a clean installation from the repository root. Python 3.12,
`uv`, Git, and a running Docker daemon must already be available.

```sh
export ASIC_TOOL_ROOT="$PWD/.asic-tools"
export UV_CACHE_DIR="$ASIC_TOOL_ROOT/uv-cache"
export PDK_ROOT="$ASIC_TOOL_ROOT/pdk"
export PDK=ihp-sg13cmos5l
export LIBRELANE_VERSION=3.1.0.dev3

git clone --branch ihp-sg13cmos5l --single-branch \
  https://github.com/TinyTapeout/tt-support-tools.git tt

uv venv --python 3.12 "$ASIC_TOOL_ROOT/venv"
uv pip install --python "$ASIC_TOOL_ROOT/venv/bin/python" \
  -r tt/requirements.txt
uv pip install --python "$ASIC_TOOL_ROOT/venv/bin/python" \
  "librelane==$LIBRELANE_VERSION"

mkdir -p "$PDK_ROOT"
git -C "$PDK_ROOT" init -q
git -C "$PDK_ROOT" fetch --depth 1 \
  https://github.com/IHP-GmbH/IHP-Open-PDK.git \
  2bbec755dc67ca3db0261c3d6163e15735d66710
git -C "$PDK_ROOT" checkout --detach FETCH_HEAD
```

Do not replace the CMOS5L PDK with the similarly named `ihp-sg13g2` process.
The existing development-container definition predates this challenge flow and
still names `ihp-sg13g2`; use the project-local setup documented here for
physical builds.

## Harden the design

Generate the merged user configuration after changing `info.yaml`, the source
list, tile count, or physical configuration:

```sh
./tt/tt_tool.py --create-user-config --ihp
```

Run the RTL-to-GDS flow:

```sh
./tt/tt_tool.py --harden --ihp
```

`tt_tool.py` obtains repository metadata before launching LibreLane. In an
exported source tree without a `.git` directory, create the configuration with
the command above and invoke the equivalent flow directly:

```sh
mkdir -p runs/wokwi
python -m librelane \
  --pdk-root "$PDK_ROOT" \
  --docker-no-tty --dockerized \
  --pdk ihp-sg13cmos5l --manual-pdk \
  --run-tag wokwi --force-run-dir runs/wokwi \
  src/config_merged.json
```

The first run may take longer because Docker must download the LibreLane tool
image. Results and detailed logs are written below `runs/wokwi/`.

Print the most useful summaries after a run:

```sh
./tt/tt_tool.py --print-warnings --ihp
./tt/tt_tool.py --print-stats --ihp
./tt/tt_tool.py --print-cell-category --ihp
```

Review mapped cell area and count, placement utilization, routing violations
and congestion, setup and hold slack, and the final DRC/LVS results. A clean
RTL simulation does not establish physical fit; these reports do.

## Verify RTL and the mapped netlist

Run the assembler and RTL regressions:

```sh
uv run pytest -q test/test_assembler.py test/test_runtime_units.py test/test_runtime_driver.py
uv run make -B -C test SIM=verilator
```

After hardening, copy the final mapped netlist into the test location and run
the functional gate-level regression:

```sh
cp runs/runtime_direct/final/nl/tt_um_protocol_emulator.nl.v \
  test/gate_level_netlist.v
uv run make -B -C test GATES=yes
```

The gate-level Makefile compiles the pinned PDK UDP primitives and generates a
build-local functional variant of its standard-cell model. This connects the
model's `delayed_*` DFF nets directly to their inputs because Icarus does not
implement the timing checks that normally drive those nets. Static timing is
still verified by LibreLane/OpenSTA; this shim affects simulation models only.

## Runtime foundation build

Preserve the baseline run while hardening the expanded runtime design:

```sh
./tt/tt_tool.py --create-user-config --ihp
mkdir -p runs/runtime_direct
python -m librelane \
  --pdk-root "$PDK_ROOT" \
  --docker-no-tty --dockerized \
  --pdk ihp-sg13cmos5l --manual-pdk \
  --run-tag runtime_direct --force-run-dir runs/runtime_direct \
  src/config_merged.json
```

The October 7, 2026 `runs/runtime_direct` build completed the configured
LibreLane flow and produced final GDS. It passed extracted timing at 20 ns in
all three corners:
setup +0.521 ns (slow) and hold +0.105 ns (fast), with zero total negative slack,
routing DRC, slew, antenna, disconnected-pin, and power-grid violations. It uses
43,642 non-filler cells, 714,224 µm² of standard-cell area, and 79.15% utilization.
All five post-route mapped tests pass against the exact final netlist. Routing
DRC, Magic DRC, and LVS error counts are 0 / 0 / 0. Final metrics are in
`runs/runtime_direct/final/metrics.json`; GDS is in
`runs/runtime_direct/final/gds/tt_um_protocol_emulator.gds`. Test commands,
metrics, and source/artifact hashes are saved in
[runtime_results.json](runtime_results.json). The 438 fanout violations remain
a signoff item; KLayout DRC/XOR, equivalence, board validation, and realistic
power/IR analysis remain open.
The final per-corner `checks.rpt` files identify 423 clock-buffer outputs and
15 signal-buffer outputs above a library fanout limit of 8 (up to 18 clock
loads and 14 signal loads). Slew and capacitance violation counts are zero;
those results do not waive the fanout constraint. Review clock clustering and
signal buffering before tapeout.
`runs/runtime_v1` and `runs/runtime_v2` are superseded exploratory builds stopped
during routing. `runs/runtime_final` routed with zero routing DRC errors but
reported -6.5407 ns worst setup slack: the external `ena` signal fed a long
combinational arbitration/write-enable path. The revised core gates instruction
issue with enable and always drains an issued access on its second clock.
`runs/runtime_timed` reduced the setup failure to -1.6939 ns but still had a
configuration-to-arbiter path. The current source removes that redundant bus
qualification: synchronous configuration clear cancels pending work and clears
the backend. `runs/runtime_closed` enabled all three PnR corners but failed
extracted slow-corner setup by -1.4498 ns on a CPU-grant-to-parameter-write path.
The current source qualifies each resource's writes directly, separating side
effects from the shared error-report decoder. `runs/runtime_direct` verifies that
revision. Earlier candidates were stopped after routing when timing failed.
None of these superseded runs establish acceptance of the current source.

## Historical baseline result

The October 2026 `runs/wokwi` build completed the configured LibreLane flow and
produced final GDS. The saved run contains 72 numbered step directories; eight
gated stages were skipped, including KLayout DRC/XOR and EQY. It used 7,403
non-filler standard cells and 132,373 µm² of
standard-cell area in a 902,417 µm² core: 14.67% utilization. Worst setup and
hold slack were +6.943 ns and +0.120 ns at the configured 20 ns clock period,
with zero total negative slack. Final route DRC, Magic DRC, LVS, antenna,
disconnected-pin, and power-grid violation counts were all zero. The post-route
mapped netlist passed the UART, SPI, and I2C cocotb regression.

The saved final metrics also report 68 maximum-fanout violations in each
timing corner (`design__max_fanout_violation__count` and its corner-specific
keys). Review the affected nets and constraints before physical signoff;
positive timing slack and zero routing DRC/LVS errors do not resolve this item.

The run is encouraging rather than unconditional tapeout signoff. KLayout DRC
and XOR are disabled in `src/config.json`; fallback SDC was used because custom
PnR/signoff SDC files are not defined; and the power/IR estimates lack activity
vectors and explicit voltage-source locations. See `docs/design.md` for the
full interpretation and remaining work.

## Continuous integration

The GitHub Actions workflow in `.github/workflows/gds.yaml` performs the same
CMOS5L build, Tiny Tapeout precheck, gate-level test, and layout-viewer build.
Use the local flow for fast iteration and CI as the reproducible submission
check.
