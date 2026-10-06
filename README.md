# Programmable Protocol Emulator ASIC

An open-source, cycle-accurate protocol engine targeting Jane Street's protocol
emulator ASIC competition and the Tiny Tapeout IHP 130 nm CMOS5L process.

Version 0.1 implements a reloadable 16-bit instruction engine, four 8-bit
registers, cycle-counted timing, branches, shifts, and direct control of eight
bidirectional protocol pins. Example firmware implements UART, SPI, and I2C.
Protocol behavior is intentionally defined by uploaded firmware: future RTL
extensions must be reusable programmable facilities, not UART-, SPI-, I2C-, or
other protocol-specific engines.

## Project status

**Last updated:** 2026-10-07

The programmable core, assembler, local CMOS5L toolchain, RTL regression,
post-route gate-level regression, and a complete RTL-to-GDS run are working.
The current physical implementation fits comfortably in the 6x4 allocation,
but the protocol implementations are still proofs of capability rather than
complete, interoperable protocol stacks.

Engineering decisions and project history are recorded in the
[work journal](#work-journal).

### Challenge protocol coverage

[Jane Street names nine protocol targets](https://blog.janestreet.com/protocol-emulator-asic-competition/).
`Verified` means the implemented scope has automated RTL and post-route
gate-level coverage; it does not imply that every optional mode or role in the
protocol standard is implemented. For this project, a protocol is not considered
fully supported until its selected role can transmit and receive arbitrary
payload data; supporting every possible controller, peripheral, host, or target
role is a separate scope decision.

| Priority | Protocol | Status | Implemented and verified scope | Next milestone |
|---|---|---|---|---|
| Baseline | UART | Partial | 8N1 transmitter, 1 Mbaud, fixed `0xA5` example | Add receive and configurable framing/baud rate |
| Baseline | SPI | Partial | Mode-0 controller, simultaneous 8-bit TX/RX | Add chip select, modes 1–3, and configurable transfers |
| Baseline | I2C | Partial | START, address write, ACK/NACK sampling, open-drain pins, clock-stretch wait | Add multi-byte read/write, repeated START, and STOP coverage |
| Stretch | Low-speed USB | Not started | — | Define packet scope and generic programmable timing requirements |
| Stretch | 10 Mbit Ethernet | Not started | — | Decide the external-PHY boundary and generic core throughput requirements |
| Suggested | JTAG | Not started | — | Implement reset, IR scan, and DR scan firmware |
| Suggested | SWD | Not started | — | Implement request, turnaround, ACK, parity, and data phases |
| Suggested | PS/2 | Not started | — | Implement host/device TX and RX with parity and ACK |
| Suggested | CAN bus | Not started | — | Define classical-CAN scope and external-transceiver interface |

### Verification snapshot

| Check | Latest result |
|---|---:|
| Assembler unit tests | 7 passed |
| RTL UART/SPI/I2C cocotb regression | Passed (Icarus and Verilator) |
| Post-route mapped-netlist UART/SPI/I2C regression | Passed |
| LibreLane CMOS5L flow | Complete; 72 recorded steps, 8 gated stages skipped |
| Non-filler standard cells | 7,403 |
| Standard-cell utilization | 14.67% |
| Worst setup slack at 20 ns | +6.943 ns |
| Worst hold slack | +0.120 ns |
| Route DRC / Magic DRC / LVS errors | 0 / 0 / 0 |
| Antenna / disconnected-pin / power-grid violations | 0 / 0 / 0 |
| Maximum-fanout violations | 68 (requires review) |

The raw results are in `runs/wokwi/final/metrics.json` after a local hardening
run. See [the design report](docs/design.md) for interpretation and
[the physical-flow guide](docs/physical_flow.md) for exact reproduction steps.

### Roadmap

- [x] Implement the programmable GPIO processor and loader.
- [x] Add an assembler and example firmware workflow.
- [x] Demonstrate UART TX, SPI mode 0, and I2C address-write signaling.
- [x] Pass RTL and post-route gate-level regression.
- [x] Complete the pinned CMOS5L RTL-to-GDS flow.
- [ ] Define and verify generic runtime data, buffering, concurrency, and timed-I/O
      facilities without adding protocol-specific RTL engines.
- [ ] Complete bidirectional, configurable UART support in firmware on the
      generic programmable architecture.
- [ ] Complete configurable, arbitrary multi-byte SPI TX/RX, modes 0–3, and
      transaction framing in firmware on the generic programmable architecture.
- [ ] Complete bidirectional, multi-byte I2C controller read/write transactions
      in firmware on the generic programmable architecture.
- [ ] Implement and verify JTAG, SWD, and PS/2.
- [ ] Implement and verify classical CAN with an external transceiver.
- [ ] Implement and verify low-speed USB.
- [ ] Implement and verify the agreed 10 Mbit Ethernet scope.
- [ ] Add randomized/reference-model and formal verification.
- [ ] Run FPGA interoperability tests with physical devices.
- [ ] Resolve remaining physical-signoff caveats.

### Known limitations and signoff gaps

- The 64x16 program memory maps to flip-flops and may be too small for complex
  USB, CAN, or Ethernet firmware.
- A single-issue instruction stream cannot sustain 10 Mbit Ethernet without a
  higher-throughput programmable execution model, generic timed-I/O
  instructions, or protocol-agnostic concurrency.
- The generic runtime-data, buffering, and concurrency architecture needed for
  continuous full-duplex traffic has not yet been designed or verified.
  Fixed-function protocol engines are explicitly outside the project
  architecture.
- KLayout DRC, layout XOR, and EQY equivalence are disabled in the current flow.
- The saved final metrics report 68 maximum-fanout violations in each timing
  corner; investigate the affected nets and constraints before physical signoff.
- Timing currently uses LibreLane's generic fallback SDC. It includes the 20 ns
  clock and 4 ns I/O delays, but explicit project signoff constraints remain to
  be defined.
- Power and IR-drop values are preliminary because realistic activity vectors
  and explicit voltage-source locations were not supplied.
- No FPGA or fabricated-silicon interoperability testing has been performed.
- The development-container template still uses `ihp-sg13g2` and LibreLane
  `3.0.0.dev44`; use the pinned local CMOS5L flow in
  [docs/physical_flow.md](docs/physical_flow.md) for physical builds.

## Environment

Python 3.12 and all Python dependencies are managed by
[uv](https://docs.astral.sh/uv/). Install either Icarus Verilog or Verilator as
the RTL simulator, then initialize the locked environment:

```sh
uv sync --locked
```

Do not install the test dependencies with `pip`; update them with `uv add
--dev` so `pyproject.toml` and `uv.lock` remain synchronized.

## Run the RTL simulation

Icarus Verilog is the default simulator:

```sh
uv run make -C test
```

To use Verilator instead:

```sh
uv run make -C test SIM=verilator
```

Run the assembler unit tests separately:

```sh
uv run pytest test/test_assembler.py
```

The default Icarus test produces `test/tb.fst`, which can be opened with
GTKWave or Surfer.

## Run the CMOS5L physical-design flow

The pinned Tiny Tapeout support tools, LibreLane version, and IHP CMOS5L PDK
are installed locally under this project rather than system-wide. See
[docs/physical_flow.md](docs/physical_flow.md) for installation, activation,
hardening, and report commands. Use that flow to measure mapped cell area,
placement utilization, routing, and timing for the 6x4 allocation. The latest
verified run fits at 14.67% utilization with clean routing DRC/LVS and positive
setup and hold slack; the measured results and caveats are recorded there.

## Project layout

- `src/`: synthesizable Verilog and the LibreLane configuration
- `firmware/`: UART, SPI, and I2C assembly programs
- `tools/assembler.py`: assembler and instruction encoder
- `test/`: cocotb testbench and simulator Makefile
- `docs/design.md`: architecture, ISA, pin ABI, and verification report
- `docs/physical_flow.md`: pinned local CMOS5L toolchain and hardening workflow
- `info.yaml`: project metadata, pinout, sources, and 6x4 tile allocation
- `.github/workflows/`: RTL tests, GDS build, precheck, and documentation jobs

## Assemble firmware

```sh
uv run python tools/assembler.py firmware/uart_tx.asm
```

See [docs/design.md](docs/design.md) for the design report and complete ISA.

## Work journal

### 2026-10-07 — Verify the full local regression suite

- Starting point: the core and physical-flow baseline commits needed a fresh
  check across all existing project tests and supported RTL simulators.
- Decision: run pytest discovery under `test/`, rebuild each simulation in its
  own ignored directory, and inspect each XML report before the next run.
- Verification: all commands used `UV_CACHE_DIR="$PWD/.asic-tools/uv-cache"`
  and `uv run --locked`. `pytest -q test` passed seven tests. Each of the
  following passed the combined UART/SPI/I2C cocotb test with zero XML
  failures/errors/skips:
  `make -B -C test SIM=icarus SIM_BUILD=sim_build/rtl_icarus`;
  `make -B -C test SIM=verilator SIM_BUILD=sim_build/rtl_verilator`;
  `make -B -C test SIM=icarus GATES=yes SIM_BUILD=sim_build/gl_icarus`
  with `PDK_ROOT="$PWD/.asic-tools/pdk"`.
  The gate-level netlist matched the saved final-run netlist byte-for-byte.
  Logs and per-run XML reports are in `/tmp/asic-full-suite-em20dcqr/`.
  `git diff --check` passed; generated build/result paths remain ignored.
- Change: refreshed the README RTL snapshot to name both passing simulators.
  No RTL, firmware, tests, dependencies, or physical results changed.
- Remaining: coverage is still the seven assembler tests and one directed
  protocol regression, exercised in three configurations. Existing protocol
  and signoff limitations remain. The gate test is functional; Icarus still
  reports unsupported PDK timing constructs. No hardening, remote CI,
  container build, or hardware interoperability run was performed.

### 2026-10-07 — Import physical-flow integration and audit saved evidence

- Starting point: the functional baseline was committed, but the CMOS5L
  configuration, physical-flow guide, build workflows, and container template
  were still untracked.
- Decision: import the existing integration without rerunning hardening or
  claiming remote CI/container verification. Keep the pinned local CMOS5L
  setup authoritative while documenting the older container template.
- Change: added `src/config.json`, the physical-flow guide, GDS/precheck/
  gate-level/viewer/docs/FPGA workflows, and development-container files.
  Updated the README and design/flow reports to record 68 maximum-fanout
  violations in each corner. Clarified the earlier 80/80 progress claim:
  the completed saved flow has 72 recorded steps and eight gated stages skipped.
  Added the container's process/LibreLane mismatch to the README limitations.
- Verification: Python assertions on `runs/wokwi/final/metrics.json` confirmed
  7,403 cells, 14.67% utilization, +6.943 ns setup/+0.120 ns hold slack,
  zero recorded route/Magic DRC, LVS, antenna and power-grid violations, and
  68 fanout violations in all three corners. Checked the final GDS, 72 numbered
  step directories, eight gated-stage skips, and `Flow complete.` in `flow.log`.
  Installed LibreLane `3.1.0.dev3`, support-tools commit
  `d66cf179e7bc4d296362ab7e2e3b344dc3c4f665`, and PDK commit
  `2bbec755dc67ca3db0261c3d6163e15735d66710` match the guide.
  `src/config.json` parsed successfully; `sh -n
  .devcontainer/copy_tt_support_tools.sh` and `git diff --check` passed.
  The preceding baseline's post-route functional regression also passed.
- Remaining: investigate fanout constraints/nets, align the container with
  CMOS5L, and verify remote CI. KLayout DRC/XOR, EQY, explicit timing
  constraints, realistic power/IR inputs, and hardware interoperability remain
  open. The saved flow was inspected, not rebuilt or promoted to signoff.

### 2026-10-07 — Import the programmable core and regression baseline

- Starting point: Git contained the ignore rules and README, while the working
  RTL, firmware, host tools, tests, and design documentation were untracked.
- Decision: preserve the two existing commits and import the functional
  baseline as one coherent milestone; import physical-flow integration
  separately rather than inventing historical implementation steps.
- Change: added the generic programmable core, Tiny Tapeout interface/metadata,
  UART/SPI/I2C example firmware, assembler, unit/cocotb tests, locked Python
  environment, RTL CI, license, repository instructions, and design/datasheet
  documentation. Corrected the stale gate-level netlist path in `test/README.md`.
- Verification: with `UV_CACHE_DIR=.asic-tools/uv-cache`,
  `uv run --locked pytest -q test/test_assembler.py` passed all seven tests and
  `uv run --locked make -B -C test` passed the combined RTL regression.
  `PDK_ROOT="$PWD/.asic-tools/pdk" UV_CACHE_DIR=.asic-tools/uv-cache
  uv run --locked make -B -C test GATES=yes` also passed against the existing
  post-route netlist. XML checks confirmed one case with no failures/errors in
  each simulation; the copied netlist matched the final-run netlist byte-for-byte.
- Remaining: these directed examples retain Partial protocol status. Generic
  runtime data/concurrency, broader ISA verification, bidirectional protocol
  firmware, and hardware interoperability remain open. CI was not run remotely;
  the physical build configuration and guide are the next import milestone.

### 2026-10-07 — Ignore VS Code workspace settings

- Starting point: the ignore rules deliberately kept `.vscode` settings and
  extension recommendations visible to Git.
- Decision: follow the user's preference to treat `.vscode/` as local editor
  configuration. This supersedes the earlier journal entry's choice to keep
  those files eligible for version control.
- Change: added `.vscode/` to `.gitignore` and updated its editor-files comment.
  No protocol, build, verification-coverage, or physical-result status changed.
- Verification: `git check-ignore -v .vscode/settings.json
  .vscode/extensions.json` matched the new rule for both files;
  `git diff --check` passed. No `.vscode` files were already tracked.
- Remaining: explicitly share any needed editor setup through documentation.

### 2026-10-07 — Keep generated files out of version control

- Starting point: the existing `.gitignore` covered the main ASIC outputs but
  left `tools/__pycache__/` files visible and omitted CI's `test/output/`.
- Decision: group rules by workflow and anchor project-specific output paths
  to the repository root. Ignore root-level assembler `.hex` output while
  keeping firmware fixtures, shared `.vscode` settings, `uv.lock`, and GTKWave
  `.gtkw` configuration eligible for version control; avoid blanket rules for
  Verilog, JSON, or physical-design file extensions.
- Change: expanded `.gitignore` for Python bytecode/caches, simulation and CI
  output, assembler output, and local editor/OS files; retained the existing
  local toolchain, PDK, hardening, submission, and generated-config exclusions.
  Protocol coverage, build commands, and physical results are unchanged.
- Verification: a Python assertion script using
  `git check-ignore --no-index --stdin` passed for 28 generated/local paths
  that must be ignored and 27 source/configuration paths that must remain
  visible. `git diff --check` and an explicit `.gitignore` trailing-whitespace
  check passed. No RTL simulation was needed for ignore-rule changes.
- Remaining: custom assembler output paths outside the root require an
  explicit ignore rule if generated files are placed there. Recheck exclusions
  when adding new build flows.

<!-- 
### 2026-10-07 — Move the work journal into the README

- Starting point: the work journal lived in `AGENTS.md`, alongside agent
  instructions, rather than in the project's reader-facing documentation.
- Decision: keep the durable engineering history at the end of `README.md`;
  `AGENTS.md` retains the rules for maintaining it.
- Change: moved all three existing entries intact, updated the journal-location
  and pre-commit instructions, and linked the journal from the README dashboard.
  References to "this file" in earlier entries retain their historical meaning:
  those entries originally lived in `AGENTS.md`.
- Verification: compared the moved historical entries byte-for-byte with their
  original content and reviewed the documentation changes. No simulation was
  required for this documentation-only move.
- Remaining: continue recording future investigations and changes in the README
  journal. Earlier statements about missing Git metadata describe the workspace
  at the time; Git metadata is now available, with no prior commits, but its
  filesystem is read-only. `git add -- AGENTS.md README.md` could not create
  `.git/index.lock`, so this milestone cannot be committed here.

### 2026-10-07 — Preserve a fully generic programmable architecture

- Starting point: the design report suggested evaluating multiple engines for
  full-duplex protocols, and the README described dedicated hardware assistance
  as a possible response to throughput limits. Those phrases could be read as
  permitting fixed-function UART, SPI, or I2C blocks, which would undermine the
  purpose of a programmable protocol emulator.
- Decision: all protocol semantics remain in uploaded firmware. Future RTL may
  add only protocol-agnostic programmable facilities, such as identical
  execution contexts, generic FIFOs, timers, event capture, shifts, and atomic
  GPIO operations. Protocol-specific engines, samplers, shifters, state
  machines, and register sets are out of scope.
- Change: made this invariant explicit in `README.md` and `docs/design.md`,
  revised the roadmap to put generic runtime/concurrency architecture before
  expanded protocol firmware, and replaced dedicated-acceleration language in
  the limitations and future-work sections. No RTL, firmware, tests, or
  physical results changed.
- Verification: searched repository sources and documentation for references
  to dedicated engines, samplers, shifters, acceleration, and multiple engines;
  reviewed the remaining uses to distinguish generic pin terminology and
  firmware data shifting from architectural recommendations. No simulation was
  required for this documentation-only decision.
- Remaining: specify the protocol-neutral host data path, buffering model,
  concurrency model, timed-I/O primitives, and GPIO ownership rules before
  implementation. The rejected alternative is a collection of configurable
  fixed-function protocol peripherals. The exported workspace still has no
  root `.git` metadata, so this milestone cannot be committed here.

### 2026-10-07 — Establish durable history and bidirectional protocol scope

- Starting point: version 0.1 had a working programmable core and one directed
  firmware demonstration each for UART, SPI, and I2C, but no durable engineering
  journal or project-specific commit-message policy.
- Decision: a protocol will only count as supported when its selected role can
  both transmit and receive arbitrary payload data. This does not automatically
  require every possible role: for example, an SPI controller can be supported
  before an SPI peripheral, and an I2C controller before an I2C target.
- Change: added the journal and Git-history rules to this file and made the
  bidirectional acceptance criterion explicit in the README roadmap. No RTL,
  firmware, tests, or physical implementation changed.
- Verification: reviewed `AGENTS.md` and `README.md` for consistent status and
  scope wording. No simulation was required for this documentation-only change.
- Remaining: design a runtime host data interface and buffering, then add UART
  RX, configurable repeated SPI transfers, and multi-byte I2C reads and writes.
  The exported workspace currently has no root `.git` metadata, so this change
  cannot be committed here.

### 2026-10-06 — Complete the version 0.1 physical baseline (retrospective)

- Implemented a reloadable 16-bit GPIO processor, assembler, and fixed example
  firmware for UART TX, SPI mode-0 TX/RX, and I2C address-write/ACK sampling.
- Verified seven assembler tests and the combined UART/SPI/I2C cocotb test at
  RTL and against the post-route mapped netlist.
- Completed all 80 LibreLane CMOS5L steps. The final run used 7,403 non-filler
  cells at 14.67% utilization, met the 20 ns clock with +6.943 ns setup and
  +0.120 ns hold slack, and reported zero route DRC, Magic DRC, LVS, antenna,
  disconnected-pin, and power-grid violations.
- Remaining caveats: protocol programs are proofs of capability rather than
  reusable transports; KLayout DRC, XOR, and EQY were disabled; fallback SDC
  was used; power/IR inputs were preliminary; and no FPGA or silicon
  interoperability test had been performed. -->
