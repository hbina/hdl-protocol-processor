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
