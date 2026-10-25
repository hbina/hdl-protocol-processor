# Protocol and runtime verification

Five baseline cocotb tests exercise the real loader/runtime pins: legacy protocols,
ECHO/XOR requests, transport boundaries, ISA/timing, and malformed records/reset
recovery. All tests work against RTL and the mapped netlist without relying on
internal hierarchical signals. The pin controller uses the same ABI library
as a board adapter: [tools/runtime.py](../tools/runtime.py).

Assembler, storage/FIFO, and controller recovery unit tests run separately:

```sh
uv run pytest -q test/test_assembler.py test/test_runtime_units.py test/test_runtime_driver.py
```

Storage tests include simultaneous FIFO operations at depths 1/3/4/64 and
record/output publication/ownership boundaries. See [runtime.md](../docs/runtime.md)
for the implemented interface and limitations.

## Setting up

1. From the repository root, run `uv sync --locked`.
2. Edit [Makefile](Makefile) when adding Verilog source files.
3. Keep [tb.v](tb.v) synchronized with the project's top-level module.

## How to run

To run the RTL simulation:

```sh
uv run make -B -C test
```

The default suite runs the five baseline integration groups plus UART/SPI/JTAG probes (ten tests total).

Study evidence below is historical unless explicitly described as a fresh check; matching saved XML/generated model artifacts are required for provenance audits.

Recorded runtime physical flow: 79.15% utilization, positive setup/hold slack at 50 MHz in three corners, zero routing/Magic DRC and LVS errors, and five mapped integration tests. See [source-bound runtime results](../docs/runtime_results.json) and [physical flow](../docs/physical_flow.md). These are historical 2026-10-07 results.

Production UART/SPI/JTAG valid-request probes exchange arbitrary payloads without firmware reload; images use 107/72/125 words. Recorded Icarus suite: ten passing tests. See [contracts and results](../docs/protocol_probe_results.md).

I2C/SWD/PS2/Ethernet model experiments record 5/2/2/6 passing groups. Their 249/230/188/280-word images exceed production capacity. See [I2C](../docs/i2c_capacity_study.md), [SWD/PS2](../docs/wave_b_results.md), and [Ethernet](../docs/ethernet_capacity_study.md).

Separate CAN RX/TX model studies record four groups each; combined TX/RX runs on an isolated 1024x18/eight-register model. Generic leaf-call/carry extensions and synthesis comparisons remain model-only. See [CAN RX](../docs/can_receive_study.md), [CAN TX](../docs/can_transmit_study.md), and [frontier results](../docs/generic_frontier_study.md).

USB studies preserve buffered-RX turnaround failures and record live RX, addressed OUT and bidirectional IN/OUT packet tests on generic models. Production capacity and interoperability remain open. See [buffered RX](../docs/usb_receive_study.md), [live RX](../docs/usb_live_study.md), [OUT](../docs/usb_out_study.md), and [IN](../docs/usb_in_study.md).

USB live TX, vendor controls, reset/deferred address and selected enumeration pass recorded model tests. The enumeration image needs 1012 words; full requests, jitter coverage, physical fit and host interoperability remain open. See [controls](../docs/usb_control_study.md), [address handling](../docs/usb_address_study.md), and [enumeration](../docs/usb_enumeration_study.md).

UART software deadlines/request validation and JTAG envelope rejection/recovery have model evidence. Their 251-/198-word images exceed production capacity. See [UART runtime](../docs/uart_runtime_study.md) and [JTAG runtime](../docs/jtag_runtime_study.md).

CAN model follow-ups record ACK-error retry, arbitration-winner reception, bounded phase correction and selected persistent error-state/bus-off recovery. Full synchronization/confinement and production fit remain open. See [ACK recovery](../docs/can_ack_recovery_study.md), [winner retry](../docs/can_winner_study.md), [resynchronization](../docs/can_resync_study.md), and [fault state](../docs/can_fault_state_study.md).

CAN firmware compaction adds selected RX error flags, post-flag counters and active-flag bit-error restarts within 1024 model words. Oversized drafts and negative comparisons remain preserved. See [RX flags](../docs/can_receive_flags_study.md), [post-flag counters](../docs/can_postflag_study.md), and [flag compaction](../docs/can_flag_compact_study.md).

CAN tail investigation preserves three old-image wire failures and the oversized 1067-word draft. A separate compact candidate fits 1024 model words; fresh seven-group RX-tail regression passes. See [original gaps](../docs/can_tail_study.md) and [compaction evidence](../docs/can_tail_compact_study.md). TX tails, overload-fault accounting and production fit remain open.

See each linked study for exact commands, filters and expected-negative comparisons. Production results and expanded-model results are separate.
