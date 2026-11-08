# Bitlogic verification

Validated locally on 2026-11-08 with rustc 1.99.0
`b940084d7 2026-09-28`, Cargo 1.99.0 `5f94df478 2026-08-27`,
and Icarus Verilog 12.0. Cargo.lock fixes the Rust dependency versions.

```sh
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
make emit example
```

The active workspace has thirty-three tests and five doctests (four compile-fail).

## Native and graph checks

Five `bitlogic/tests/logic.rs` integration tests include independent comparisons
of native Rust and graph evaluation. Cases cover every input of a three-bit
conditional transform, a minimum/flag function, bit slicing/concatenation and
bounded loop expansion. The graph interpreter exhausts all 64 input pairs for
each of eleven binary operations at three bits. Tests also check unsigned wrap
behavior, 64-bit boundaries, oversized shifts, composition identity, mismatched
port shapes, out-of-range input values, and invalid widths/module names.

## Emitted combinational HDL

One Icarus test checks all 128 combinations of a conditional transform against an
independent Verilog oracle. A separate operator test checks 2,725 cases across
one-, three-, and 64-bit arithmetic/bitwise/comparison operations, slices,
concatenation, and shift boundaries. The tests execute generated HDL using
`iverilog -g2012` and `vvp`, require successful exit, and check success markers.
They do not infer clock behavior or physical timing.

## Bounded set example

Two tests in `crates/bitlogic/examples/set.rs` independently check every one of
256 membership bitmaps, eight keys, and four operations (8,192 cases). A Rust
`BTreeSet` oracle supplies the expected next set and pre-operation membership.
One test checks native Rust and IR evaluation; the other checks generated HDL
with Icarus against the oracle's expected values. This includes duplicate inserts,
absent removals, empty/full sets, both boundary keys, and clear for every key.
The example's `test = true` Cargo setting includes these in the workspace tests.

`cargo run --locked -p bitlogic --example set -- demo` also passes its native/IR
assertions across a sequence of operations. The `verilog` mode emits `set_step`,
which compiles with `iverilog -g2012 -s set_step`. No state registers are emitted.

## Protocol processor example

Twenty-five tests in `examples/protocol_processor/tests.rs` and its child modules participate in the workspace
suite through Cargo's `test = true` setting. All pass on 2026-11-08. The reference
machine uses ordinary integers and a separate decoder, not the DSL or host decoder.
Protocol waveforms and peer responses are specified independently of instruction
execution, then checked against native Rust, IR and generated HDL.

| Check | Exact local evidence |
|---|---|
| ISA and image validation | Every nonzero 16-bit WAIT encoding; all 65,536 SET_PINS mask/value combinations; expected encoding constants, invalid operand constructors, malformed/reserved bits, capacity, final HALT, and branch-target rejection |
| Transition equivalence | 327,190 reference/native/IR/combinational-Icarus cases, including every WAIT issue/countdown value, masks, PC boundaries, halted/wait/fault priority, scratch aliases/truth tables, input sampling, runtime control flow, pin configuration, atomic sample/output updates and word parity; includes 65,536 configuration mask/enable combinations |
| UART TX | 6,144 one-byte programs (256 bytes × 8 pins × periods 1/2/8), each with zero and nonzero initial output values in native/IR; independent serialized-frame oracle; clocked HDL uses reset state |
| UART TX clocked coverage | 326,345 edges including all 6,144 programs, empty/multi-byte cases and a full period-65536 empty transmission |
| Core clocked boundaries | 801 edges for reset during WAIT/HALT/fault, restart, unused ROM, HALT at PC=255 and increment faults there |
| Runtime polling | 8,836 clocked edges with matching native/IR; input transitions swept across polling/timeout boundaries for pins 0/7, attempts 1/2/5 and gaps 1/2/8; infinite-loop runner limit checked |
| SPI | 2,112 independent peer/waveform programs: all bytes × four modes × two orders at half-period 2, plus selected bytes at 3/8; 84,064 clocked edges; received-byte reconstruction and pin/clock/select scheduling |
| UART RX | 797 independent frame/error scenarios; all bytes and polling phases at period 16, selected bytes at 8/32, adjacent next-frame start, false start, bad stop, no-start timeout; 135,340 clocked edges |
| I²C | 684 independent resolved-bus scenarios: all 256 write bytes and 256 read responses, all 112 ordinary addresses, two pin mappings, stretching each of 19 clock releases, address/data NACK, busy clock/data, and timeout edges; 119,794 clocked edges |
| Pad reset | 19 clocked edges verify reset while the controller drives SCL and subsequent released pads; atomic configuration expected values, reserved bits and label/image errors checked separately |
| JTAG | 672 TAP-model scenarios: IR/DR scans of widths 1/4/8/16/32 from all 16 states, all byte values at width 8, captured data and final Idle; 83,808 clocked edges after shared falling/setup edge compilation |
| PS/2 | 272 independent resolved-bus scenarios: all 256 bytes, alternate pins/hold and initial inhibit, inhibit after each of the first ten bits, host request, timeout, odd parity and released exits; 32,482 clocked edges |
| SWD | 549 independent push-pull target scenarios: DP/AP request fields, all ACKs, read/write, parity failure, WAIT retry/exhaustion and alternate pins/holds; 119,250 clocked edges with ownership checked before/after every edge |
| SWD reset/atomic instruction | 298 clocked edges check 56-high/two-low reset clocks and sampling a pin's old level while atomically changing its output; literal encodings and PARITY_WORD source/destination aliases checked independently |
| JTAG sequence | Four-bit IR then 32-bit DR from all 16 initial states, selected instruction preserved at DR capture and both results retained; 4,032 clocked edges |
| Composition | 24 independent combined UART/SPI waveforms, including explicit shared-pin handoff; 1,952 edges; polling-success/timeout continuation adds 27 edges; resource/exit/capacity/rollback and all branch relocation forms tested |
| UART batch RX | 780 complete adjacent-frame scenarios: all byte values and polling phases in two-frame batches at period 8, six-frame batches at 8/16/32, and a later bad stop preserving earlier bytes; 143,532 clocked edges |

Clocked tests total 1,060,580 edge observations. They stream test vectors into an
Icarus testbench that fetches from `rom[pc]`; they do not bypass the fetch interface
by supplying the expected next instruction manually. Every ROM load first fills
unused words with zero. Checkers require simulator success and exact vector counts.
Resolved-bus cases instantiate `protocol_pads` with tri-state drivers and `tri1`
pull-ups; external peer drivers and expected sampled inputs are independently
specified. The simulator checks the resolved input before each execution edge,
all state including enables afterward, and that open-drain outputs never drive
high. Push-pull SWD cases additionally check that target and host never own SWDIO
simultaneously, including matching values. I²C's target decodes SCL/SDA transitions without reading PC/instructions;
JTAG's peer uses a sixteen-state TAP table; PS/2's host checks framing and parity.
Combinational tests separately inject arbitrary boundary states. These finite
checks do not exhaust the machine's complete state space or establish formal
equivalence. Maximum SPI/RX period construction is tested, but their complete
maximum-period waveforms are not simulated.

`cargo run --locked -p bitlogic --example protocol_processor -- stats` reports
2,314 IR nodes and 107,058 bytes for the combinational module in this revision;
the wrapper is additional. This is not a synthesis area or timing measurement.
See the [processor contract](protocol_processor.md) and [protocol interfaces](protocols.md).

## Generic mapping and mapped regression

`make processor-mapped-test` passes with the locked optional uv tools. Yosys 0.70
maps the core to 2,527 generic logic cells and 122 synchronous-reset flops, checks
structure and emits a Verilog netlist. The same 25 processor tests pass with the
mapped modules: 327,190 transition vectors and 1,060,580 clocked observations.
This is a second implementation path, not additional unique input coverage or a
formal equivalence proof. The pad module remains a logical simulation model.
Exact commands, tool versions, cell types, tri-state warning and physical limits
are recorded in the [synthesis baseline](processor_synthesis.md).

## Frontend and borrowing checks

A macro unit test requires specific diagnostics for unsupported syntax,
incomplete outputs, reads before definition, width/slice errors, and expansion
limits. Four compile-fail doctests cover incomplete output definitions, writing
an input reference, and Rust E0499/E0502 aliasing errors. One executable doctest
checks native evaluation, graph evaluation, and HDL construction.

## Build and CI

`make emit` writes `build/select_logic.v`; `make example` prints the HDL example.
The GitHub workflow installs Icarus, checks formatting and Clippy, runs workspace
tests, and emits the HDL example. No remote CI execution is claimed.

## Limits and retired coverage

The earlier RHDL ISA, processor, timed frontend, and processor backend were
removed, along with their tests. The new library example above has its own
verification. Historical processor/waveform results are not active bitlogic
coverage. See [project history](history.md).

There is no native/IR-to-HDL formal proof, technology place-and-route, physical
timing closure, FPGA fit, board test, CDC integration or electrical validation.
These finite functional tests do not establish correctness for every possible
source program or target.
