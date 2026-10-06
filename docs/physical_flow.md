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
uv run pytest -q test/test_assembler.py
uv run make -B -C test SIM=verilator
```

After hardening, copy the final mapped netlist into the test location and run
the functional gate-level regression:

```sh
cp runs/wokwi/final/nl/tt_um_protocol_emulator.nl.v \
  test/gate_level_netlist.v
uv run make -B -C test GATES=yes
```

The gate-level Makefile compiles the pinned PDK UDP primitives and generates a
build-local functional variant of its standard-cell model. This connects the
model's `delayed_*` DFF nets directly to their inputs because Icarus does not
implement the timing checks that normally drive those nets. Static timing is
still verified by LibreLane/OpenSTA; this shim affects simulation models only.

## Latest verified result

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
