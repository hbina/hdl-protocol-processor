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

Production UART/SPI/JTAG valid-request probes exchange arbitrary payloads without firmware reload; images use 107/72/125 words. Recorded Icarus suite: ten passing tests. See [contracts and results](docs/protocol_probe_results.md).

I2C/SWD/PS2/Ethernet model experiments record 5/2/2/6 passing groups. Their 249/230/188/280-word images exceed production capacity. See [I2C](docs/i2c_capacity_study.md), [SWD/PS2](docs/wave_b_results.md), and [Ethernet](docs/ethernet_capacity_study.md).

Separate CAN RX/TX model studies record four groups each; combined TX/RX runs on an isolated 1024x18/eight-register model. Generic leaf-call/carry extensions and synthesis comparisons remain model-only. See [CAN RX](docs/can_receive_study.md), [CAN TX](docs/can_transmit_study.md), and [frontier results](docs/generic_frontier_study.md).

USB studies preserve buffered-RX turnaround failures and record live RX, addressed OUT and bidirectional IN/OUT packet tests on generic models. Production capacity and interoperability remain open. See [buffered RX](docs/usb_receive_study.md), [live RX](docs/usb_live_study.md), [OUT](docs/usb_out_study.md), and [IN](docs/usb_in_study.md).

USB live TX, vendor controls, reset/deferred address and selected enumeration pass recorded model tests. The enumeration image needs 1012 words; full requests, jitter coverage, physical fit and host interoperability remain open. See [controls](docs/usb_control_study.md), [address handling](docs/usb_address_study.md), and [enumeration](docs/usb_enumeration_study.md).

UART software deadlines/request validation and JTAG envelope rejection/recovery have model evidence. Their 251-/198-word images exceed production capacity. See [UART runtime](docs/uart_runtime_study.md) and [JTAG runtime](docs/jtag_runtime_study.md).

CAN model follow-ups record ACK-error retry, arbitration-winner reception, bounded phase correction and selected persistent error-state/bus-off recovery. Full synchronization/confinement and production fit remain open. See [ACK recovery](docs/can_ack_recovery_study.md), [winner retry](docs/can_winner_study.md), [resynchronization](docs/can_resync_study.md), and [fault state](docs/can_fault_state_study.md).

Saved study records retain their original hashes and outcomes. Source formatting has changed since some recorded runs; historical evidence is not a fresh provenance check of this checkout. The production physical-source hashes remain unchanged.

### Challenge protocol coverage

All listed support is partial; no full protocol or board interoperability claim is made.

| Protocol | Status | Scope |
|---|---|---|
| UART | Partial | Production valid-request TX/RX probe; mapped fixed-byte baseline only |
| SPI | Partial | Production valid-request TX/RX probe; mapped fixed-byte baseline only |
| I2C | Partial | Production address example; TX/RX on larger model only |
| JTAG | Partial | Valid-request TAP/IR/DR probe |
| SWD | Partial | Larger model only |
| PS/2 | Partial | Larger model only |
| 10 Mbit Ethernet | Partial | Buffered minimum-frame model only |
| CAN bus | Partial | Larger generic models only |
| Low-speed USB | Partial | Larger generic models only |

### Roadmap

- [x] Add bounded runtime transport and memory interface.
- [x] Harden runtime design across three process corners.
- [x] Add runtime UART SPI and JTAG probes.
- [x] Measure I2C SWD PS2 and Ethernet capacity limits.
- [x] Add CAN receive transmit and generic frontier models.
- [x] Develop USB packet reception and transmission.
- [x] Add USB control transfers and enumeration.
- [x] Validate UART and JTAG runtime requests.
- [x] Add CAN retry synchronization and fault confinement.
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
