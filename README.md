# Programmable Protocol Emulator ASIC

An open-source, cycle-accurate protocol engine targeting Jane Street's protocol
emulator ASIC competition and the Tiny Tapeout IHP 130 nm CMOS5L process.

Version 0.2 implements a reloadable 128-word 16-bit instruction engine, four
8-bit registers, 256-byte data memory, bounded runtime queues, an asynchronous
request/acknowledgement interface, and direct control of eight protocol pins. Example firmware implements UART, SPI, and I2C.
Protocol behavior is intentionally defined by uploaded firmware: future RTL
extensions must be reusable programmable facilities, not UART-, SPI-, I2C-, or
other protocol-specific engines.

## Project status

**Last updated:** 2026-10-25

128-word production core; 256-byte data store; one outstanding request; 64-entry input/output queues; ECHO/XOR firmware and host ABI. Baseline verification: 16 assembler, 5 storage/FIFO and 4 controller units; five RTL integration groups. See [runtime specification](docs/runtime.md).

Recorded runtime physical flow: 79.15% utilization, positive setup/hold slack at 50 MHz in three corners, zero routing/Magic DRC and LVS errors, and five mapped integration tests. See [source-bound runtime results](docs/runtime_results.json) and [physical flow](docs/physical_flow.md). These are historical 2026-10-07 results.

Saved study records retain their original hashes and outcomes. Source formatting has changed since some recorded runs; historical evidence is not a fresh provenance check of this checkout. The production physical-source hashes remain unchanged.

### Challenge protocol coverage

All listed support is partial; no full protocol or board interoperability claim is made.

| Protocol | Status | Scope |
|---|---|---|
| UART | Partial | Fixed-byte TX example |
| SPI | Partial | Mode-0 byte example |
| I2C | Partial | Address write/ACK/stretch example |
| JTAG | Not started | Pending |
| SWD | Not started | Pending |
| PS/2 | Not started | Pending |
| 10 Mbit Ethernet | Not started | Pending |
| CAN bus | Not started | Pending |
| Low-speed USB | Not started | Pending |

### Roadmap

- [x] Add bounded runtime transport and memory interface.
- [x] Harden runtime design across three process corners.
- [ ] Add runtime UART SPI and JTAG probes.
- [ ] Measure I2C SWD PS2 and Ethernet capacity limits.
- [ ] Add CAN receive transmit and generic frontier models.
- [ ] Develop USB packet reception and transmission.
- [ ] Add USB control transfers and enumeration.
- [ ] Validate UART and JTAG runtime requests.
- [ ] Add CAN retry synchronization and fault confinement.
- [ ] Extend CAN error flags counters and firmware compaction.
- [ ] Compact CAN receive tails and preserve overload comparisons.
- [ ] Add protocol acceptance audit and exploration budgets.
- [ ] Complete protocol contracts and production capacity/physical decisions.
- [ ] Add randomized/reference-model and formal verification.
- [ ] Validate FPGA/board interoperability and complete physical signoff.

### Known limitations and signoff gaps

- Production uses 128x16 standard-cell program storage and four registers; larger study models are unsupported ASIC configurations.
- Runtime permits one fully buffered request with at most 64 input/output entries; streaming, cancellation and concurrency are absent.
- No FPGA or fabricated-silicon interoperability tests have been performed.
- KLayout DRC, layout XOR and EQY equivalence remain disabled. Power/IR-drop results lack realistic activity and explicit voltage-source locations.
- Runtime physical results retain 438 maximum-fanout violations; board CDC/MTBF and board-specific timing remain open. Passing setup/hold and slew does not close these risks.
- The development container still targets the older ihp-sg13g2 template; use the documented pinned local CMOS5L flow.

## Environment

Python 3.12 and all Python dependencies are managed by
[uv](https://docs.astral.sh/uv/). Install either Icarus Verilog or Verilator as
the RTL simulator, then initialize the locked environment:

```sh
uv sync --locked
```

Do not install the test dependencies with `pip`; update them with `uv add
--dev` so `pyproject.toml` and `uv.lock` remain synchronized.

Format Python code with Ruff:

```sh
uv run ruff format .
```

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
uv run pytest test/test_assembler.py test/test_runtime_units.py test/test_runtime_driver.py
```

The default Icarus test produces `test/tb.fst`, which can be opened with
GTKWave or Surfer.


See [runtime.md](docs/runtime.md) for the current ISA/ABI and [physical_flow.md](docs/physical_flow.md) for physical build commands.
