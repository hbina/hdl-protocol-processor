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

The default suite includes the five baseline tests, three host-driven UART
probe tests, one host-driven SPI probe test and one JTAG TAP scan test. These compact firmware images
test arbitrary payload TX/RX on the unchanged core; they accept valid runtime
requests and do not yet implement full envelope validation. See
[probe contracts and results](../docs/protocol_probe_results.md).
Select a probe alone with `COCOTB_TEST_MODULES=test_uart_probe` or
`COCOTB_TEST_MODULES=test_spi_probe`. The physical-flow baseline previously ran
only the five tests in module `test`; new probe gate coverage remains pending.

The [I2C capacity study](../docs/i2c_capacity_study.md) is separate from this
production-RTL suite. Its 249-word firmware fails the actual 128-word assembler
limit; `uv run --locked python study/protocol_exploration/run_i2c.py --expanded-model`
explicitly tests an isolated 256-word core model. CI runs that experiment as
a separate step. Passing it is not evidence of I2C TX/RX on the current ASIC.

[Wave B](../docs/wave_b_results.md) adds JTAG to production RTL regression.
`COCOTB_TEST_MODULES=test_jtag_probe` selects its TAP/IR/DR test alone.
SWD and PS/2 candidates exceed the actual 128-word limit; run their explicit
capacity models with `uv run --locked python study/protocol_exploration/run_wave_b.py swd --expanded-model`
or replace `swd` with `ps2`. CI is configured to run these as separate studies;
they do not add SWD/PS2 coverage to the current ASIC.

The [Ethernet study](../docs/ethernet_capacity_study.md) uses a separate 512-word
model and generic nine-bit long branch extension. Run
`uv run --locked python study/protocol_exploration/run_wave_c.py ethernet --expanded-model`.
Its six tests cover addressing, buffered minimum-frame TX/RX/FCS, errors and
clock timing. The 280-word image fails production capacity. CI keeps this
experiment separate; the production RTL suite remains ten tests.

The [CAN receive study](../docs/can_receive_study.md) uses the same explicit
512-word generic-address model, with a separate runner:
`uv run --locked python study/protocol_exploration/run_can.py can --expanded-model`.
Four tests cover RX/live CRC/ACK, faults/recovery, phase/frequency and timeout.
The 335-word RX image fails production capacity. This is not CAN TX coverage
or complete CAN node conformance, and does not add to the native ten tests.

The [CAN TX study](../docs/can_transmit_study.md) adds four separate model tests:
`uv run --locked python study/protocol_exploration/run_can_tx.py can_tx --expanded-model`.
They cover frame generation, monitoring/ACK/arbitration-loss release, peer
timing and busy timeout. The 318-word TX image is separate from RX; a combined
622-word source fails even 512-word assembly and did not run on that model. These are not
alternating TX/RX or complete CAN conformance results.

The [USB packet study](../docs/usb_receive_study.md) has two separate 512-word
models, each with five packet-level tests:
`uv run --locked python study/protocol_exploration/run_usb_rx.py usb_rx --expanded-model`
and `uv run --locked python study/protocol_exploration/run_usb_rx_compact.py usb_rx_compact --expanded-model`.
Both still fail their separate `--deadline-check` requirement test. Packet
validation and diagnostic ACK waveform passes do not imply enumeration,
control-transfer success or USB timing compliance. The 400-/391-word images
also fail production capacity. CI runs the functional studies; failing deadline
reproducers are documented separately, with their source-bound evidence.

The [generic frontier model](../docs/generic_frontier_study.md) uses 1024×18
program words and eight registers. Run `uv run --locked pytest -q test/test_frontier_assembler.py`
for three encoding tests, `uv run --locked python study/protocol_exploration/run_frontier.py can_duplex --expanded-model`
for the ISA diagnostic and combined CAN alternation/recovery, and
`uv run --locked python study/protocol_exploration/run_frontier_legacy.py can_duplex --expanded-model`
for the ten legacy tests on that model. Production RTL/assembler are unchanged;
there is no mapped or physical frontier proof. CI keeps these runs separate.

The [live USB study](../docs/usb_live_study.md) adds a generic one-level CALL/RET
model. Run `uv run --locked python study/protocol_exploration/run_usb_live.py usb_live --expanded-model`
for five tests, including packet ACK deadlines and actual sample timing;
`uv run --locked pytest -q test/test_usb_live_units.py` for four new units; and
`uv run --locked python study/protocol_exploration/run_call_legacy.py can_duplex --expanded-model`
for the ten legacy tests on that model. This is packet-level timing evidence,
not USB enumeration or production timing/area proof.

The [addressed USB study](../docs/usb_out_study.md) adds generic carry shifts.
Run `uv run --locked pytest -q test/test_carry_frontier.py` for three units,
`uv run --locked python study/protocol_exploration/run_usb_dense.py usb_dense --expanded-model`
for six compact receiver/ISA tests, and
`uv run --locked python study/protocol_exploration/run_usb_out.py usb_out --expanded-model`
for four addressed OUT/SETUP tests, including minimum token-to-data spacing.
`uv run --locked python study/protocol_exploration/run_carry_legacy.py can_duplex --expanded-model`
runs the ten legacy tests on the carry model. CI records these separately.
IN payloads, reset, endpoint state, enumeration and production fit remain open.

The [bidirectional USB follow-up](../docs/usb_in_study.md) runs IN and OUT/SETUP
on one image. Run `uv run --locked pytest -q test/test_usb_in_units.py` for two
units and `uv run --locked python study/protocol_exploration/run_usb_in.py usb_in --expanded-model`
for six test groups, including the prior OUT tests, arbitrary IN payloads,
host ACK/retry, waveform timing and alternating directions without reload.
All packet processing remains firmware. Autonomous endpoint state, reset,
enumeration and production physical fit remain unresolved.

The [live TX/control study](../docs/usb_control_study.md) removes waveform
precomputation and tests an autonomous address0/EP0 vendor write/status/read/status
pair. Run `uv run --locked pytest -q test/test_usb_control_units.py` for two units,
`uv run --locked python study/protocol_exploration/run_usb_stream.py usb_stream --expanded-model`
for six live packet groups, and
`uv run --locked python study/protocol_exploration/run_usb_control.py usb_control --expanded-model`
for three control groups. The runtime host remains inactive between USB control
stages. Reset, standard requests, address changes and enumeration remain open.

The [reset/address study](../docs/usb_address_study.md) adds sustained-SE0 reset
and deferred SET_ADDRESS entirely in firmware. Run
`uv run --locked pytest -q test/test_usb_address_units.py` for two units and
`uv run --locked python study/protocol_exploration/run_usb_address.py usb_address --expanded-model`
for six groups, including the three prior control groups, full reset/recovery,
pending-address and partial-packet cancellation, and assigned-address readback.
Descriptors, configuration and enumeration remain open; production RTL is unchanged.

The [enumeration study](../docs/usb_enumeration_study.md) adds device/configuration
descriptors, DATA toggle progression, configuration state and an independent host
enumeration sequence followed by arbitrary vendor traffic. Run
`uv run --locked pytest -q test/test_usb_enum_units.py` for two units and
`uv run --locked python study/protocol_exploration/run_usb_enum.py usb_enum --expanded-model`
for ten groups. The retained slower firmware reproduces a short-gap failure:
`uv run --locked python study/protocol_exploration/run_usb_enum.py usb_enum --expanded-model --unoptimized-ack --test-filter test_descriptor_short_interpacket_gap`.
That command is expected to fail; the ordinary CI run uses the fixed image.
These remain isolated-model results, with production fit and full USB compliance open.

For a provenance/capacity check of the saved exploration snapshots, run
`uv run --locked python tools/audit_exploration.py --output docs/protocol_acceptance_results.json`.
It requires the matching saved XML/model artifacts and rejects changed hashes.
It checks seventeen passing source/XML records and reruns seventeen assembly-capacity failures,
not the simulations, and does not
prove full protocol acceptance. See the [requirement audit](../docs/protocol_acceptance_audit.md).

The [UART runtime contract study](../docs/uart_runtime_study.md) adds request
validation and exact software-clock windows to the eight-register model.
Run `uv run --locked pytest -q test/test_uart_runtime_units.py` for two units and
`uv run --locked python study/protocol_exploration/run_uart_runtime.py --expanded-model`
for six groups in `test/test_uart_runtime.py`. Without `--expanded-model`, the
runner reproduces the251-word/128-word capacity failure. This module is in CI's
separate model step, not the production Makefile regression; mapped/Verilator/
board verification and the named production image remain blocked.

The [validated JTAG study](../docs/jtag_runtime_study.md) adds envelope/length
rejection with no per-request pin activity or TAP state change. Run
`uv run --locked pytest -q test/test_jtag_runtime_units.py` and
`uv run --locked python study/protocol_exploration/run_jtag_runtime.py jtag_runtime --expanded-model`.
Two groups cover valid scans and 30 invalid requests, with successful scans after
rejection. Without the model flag, assembly fails198>128. Production retains the
original125-word probe; the validated image has no mapped/board proof.

The [CAN ACK-recovery study](../docs/can_ack_recovery_study.md) adds active flags
at the ACK-error boundary, at most three attempts, overlapping dominant flags
and subsequent RX after exhaustion or delimiter timeout. Run
`uv run --locked pytest -q test/test_can_recovery_units.py` and
`uv run --locked python study/protocol_exploration/run_can_recovery.py can_recovery --expanded-model`.
Three groups pass on the existing generic1024×18/eight-register model.
Without the model flag, production assembly fails701>128. This frozen candidate
lacks winner RX/retry; the follow-up below adds it. Resynchronization and full
fault confinement remain open. CI preserves its artifacts separately.

The [CAN winner study](../docs/can_winner_study.md) adds winner reception/ACK,
retained-payload retry and a shared three-attempt cap with existing generic
instructions and data RAM. Run `uv run --locked pytest -q test/test_can_winner_units.py`
and `uv run --locked python study/protocol_exploration/run_can_winner.py can_winner --expanded-model`.
Three groups pass, covering all11 identifier loss positions, repeated winners,
33-byte exhaustion, bad winner CRC and combined arbitration/ACK retries.
Production assembly fails811>128. Resynchronization, full error handling and
continuous multi-node service remain open; mapped/board evidence is absent.

The [CAN RX phase study](../docs/can_resync_study.md) tests bounded falling-edge
correction with existing generic instructions. Run
`uv run --locked pytest -q test/test_can_resync_units.py` and
`uv run --locked python study/protocol_exploration/run_can_resync.py can_resync --expanded-model`.
Three groups pass at selected ±5,000 ppm rates,400 ns phase steps, DLC0–8 and
winner/retry compatibility. Production assembly fails819>128. The retained
comparison is expected to fail with a missing ACK:
`uv run --locked python study/protocol_exploration/run_can_resync.py can_resync --expanded-model --fixed-clock --test-filter test_clock_drift_regression`.
It saves separate negative XML/provenance; CI runs the positive suite. Full CAN
SJW/TX timing, error confinement and physical/board proof remain open.

The [CAN fault-state study](../docs/can_fault_state_study.md) uses the existing
generic call model for persistent counters, selected TX error flags, bus-off and
monitored recovery. Run
`uv run --locked pytest -q test/test_can_fault_units.py test/test_can_fault_equal_units.py`
and `uv run --locked python study/protocol_exploration/run_can_fault_equal.py can_fault_equal --expanded-model`.
Five groups cover counter/passive thresholds, the silent ACK exception, REC
saturation, interrupted recovery and bounded equal-polarity waits. Production
assembly fails1,020>128. The fixed-six-bit prototype must fail the stronger check:
`uv run --locked python study/protocol_exploration/run_can_fault_equal.py can_fault_equal --expanded-model --fixed-flag --test-filter test_persistent_passive_ack_exception`.
Its1,092-word inlined comparison also exceeds the1,024-word model. CI runs the
corrected positive suite. RX error flags, other counter/timing rules and actual
ASIC/board support remain open.

The [CAN RX-flag study](../docs/can_receive_flags_study.md) adds timed CRC/stuff/
selected form-error flags, sharing generic firmware sequencing. Run
`uv run --locked pytest -q test/test_can_rx_flags_units.py` and
`uv run --locked python study/protocol_exploration/run_can_rx_flags.py can_rx_flags --expanded-model`.
Five groups cover wire timing, pack/unpack/phase regressions, passive saturation,
winner/retry traffic and bus-off recovery. The1,069-word candidate fails model
capacity; firmware compaction produces1,021 words, still above production128.
The older local-error image must fail the CRC-flag check:
`uv run --locked python study/protocol_exploration/run_can_rx_flags.py can_rx_flags --expanded-model --local-errors --test-filter test_receiver_error_flags`.
Remaining counter/timing/EOF/overload/busy-bus rules and actual ASIC/board support
remain open; CI runs the compact positive suite separately.

The [CAN post-flag counter study](../docs/can_postflag_study.md) adds receiver
first-post-flag+8 and repeated prolonged-dominant+8 accounting in generic firmware.
Run `uv run --locked pytest -q test/test_can_postflag_units.py` and
`uv run --locked python study/protocol_exploration/run_can_postflag.py can_postflag --expanded-model`.
Five groups cover RX/TX increments, mixed runs, thresholds/saturation, passive
ACK exceptions, bus-off/recovery and normal-traffic regressions. Eighteen saved
timing rows retain400-clock delimiter spacing. The1,023-word candidate fits
the model with one word free;1,034-/1,028-word attempts exceed model capacity
and production rejects1,023>128. The older image must fail REC1 versus9:
`uv run --locked python study/protocol_exploration/run_can_postflag.py can_postflag --expanded-model --prior-counters --test-filter test_receiver_postflag_dominance`.
CI runs the positive suite and preserves timing/XML/source evidence. Flag
bit-error accounting and broader timing/EOF/overload/busy-bus behavior remain open.

The [active-flag bit-error investigation](../docs/can_flag_bit_study.md) is an
expected-negative experiment on the old1,023-word image:
`uv run --locked python study/protocol_exploration/run_can_flag_bit.py can_flag_bit --expanded-model --prior-monitor`.
It reports two active-flag counter failures and one passive dominance control
pass. Recessive RXD is forced during a commanded dominant TXD bit to model a
transceiver fault. The new1,076-word draft is **unverified** and exceeds both
model1,024 and production128; `--expanded-model` without `--prior-monitor`
rejects it before RTL simulation. Run
`uv run --locked pytest -q test/test_can_flag_bit_units.py` for listing freshness
and real size diagnostics. This unit is in CI; the expected-negative simulator
run is deliberately separate from the passing experiment suites.

The [compacted flag-error study](../docs/can_flag_compact_study.md) produces a
1,024-word image using the existing generic model, with zero free words. Run
`uv run --locked pytest -q test/test_can_flag_compact_units.py` and
`uv run --locked python study/protocol_exploration/run_can_flag_restart.py can_flag_restart --expanded-model`.
Five groups verify all six RX/TX flag positions, good traffic afterward, passive
dominance, repeated faults and threshold-crossing restarts. Five prior counter
groups pass with
`uv run --locked python study/protocol_exploration/run_can_flag_compact.py can_flag_compact --expanded-model --suite postflag`.
Two selected wire/pack/phase groups pass with
`uv run --locked python study/protocol_exploration/run_can_flag_restart.py can_flag_restart --expanded-model --suite rx_flags --test-filter 'test_receiver_error_flags|test_compact_pack_unpack_and_phase'`.
The other three RX groups are filtered out and are not claimed as rerun. CI
runs these positive suites and preserves source/XML/timing artifacts. The older
negative now has its RX sample observer enabled; it retains the same two counter
failures and passive control pass. Production still rejects1,024>128.

The [CAN tail investigation](../docs/can_tail_study.md) is an expected-negative
wire suite: `uv run --locked python study/protocol_exploration/run_can_tail.py can_tail --expanded-model --prior-monitor`.
It reproduces three gaps (last EOF, overload, third-intermission SOF) and passes
one ordinary-frame control for0/1/8-byte payloads. Run
`uv run --locked pytest -q test/test_can_tail_units.py` for source freshness and
actual1,067>1,024/128 size diagnostics. The RX draft has no behavioral proof;
TX tail and overload-flag fault rules are unfinished. The unit is in CI; the
expected-negative simulator command is separate from passing suites.

Run the command from the repository root. Add `SIM=verilator` to use
Verilator instead of Icarus Verilog.

To run gate-level simulation, first harden your project using the
[physical-flow guide](../docs/physical_flow.md), then copy the final netlist
from the repository root:

```sh
cp runs/runtime_direct/final/nl/tt_um_protocol_emulator.nl.v test/gate_level_netlist.v
```

With `PDK_ROOT` set as described in that guide, run:

```sh
uv run make -B -C test GATES=yes
```

If you wish to save the waveform in VCD format instead of FST format, edit tb.v to use `$dumpfile("tb.vcd");` and then run:

```sh
make -B FST=
```

This will generate `tb.vcd` instead of `tb.fst`.

## How to view the waveform file

Using GTKWave

```sh
gtkwave tb.fst tb.gtkw
```

Using Surfer

```sh
surfer tb.fst
```

## Compact CAN tail evidence

The [compact tail study](../docs/can_tail_compact_study.md) freshly passes seven
selected RX-tail groups on the isolated 1024-word model. Run
`uv run --locked python study/protocol_exploration/run_can_tail_compact.py can_tail_compact --expanded-model`
and `uv run --locked pytest -q test/test_can_tail_compact_units.py`.
Historical regressions retain their original hashes; the aggregate provenance
audit currently rejects source/XML drift. See
[pre-commit verification](../docs/commit_verification.json) for fresh results.
