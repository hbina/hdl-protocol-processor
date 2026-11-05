# Initial RHDL protocol processor verification

Validated locally on 2026-11-05 with rustc 1.99.0
`b940084d7 2026-09-28`, Cargo 1.99.0 `5f94df478 2026-08-27`,
and Icarus Verilog 12.0. RHDL dependencies are pinned in the root Cargo manifest;
the root lockfile fixes transitive dependency versions.

```sh
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
make emit example
```

All commands pass locally: 19 tests and nine doctests (seven compile-fail).
The earlier 2026-10-31 run used `CARGO_HOME=/tmp/jane-rhdl-cargo`; the current run
uses the normal Cargo cache. Neither location is an application requirement.

## Independent comparisons

`protocol-isa` implements a native integer reference machine without depending
on RHDL. The processor's `step` function implements the instruction contract
using RHDL bit types. Every byte, every pin and bit periods of 1, 2 and 8 produce
6,144 single-byte programs. Their execution checks both state agreement and an
independent UART waveform expectation: idle, start, data, stop, exact hold time,
and preservation of unrelated pins. There are 247,808 waveform cycle checks.
These periods exercise one-cycle execution and off-by-one timing; no physical
clock speed is inferred from them.
The programs now come from the `#[protocol]` UART frontend. For every UART case,
the native annotated function's effects also agree with the generated compiler
path's IR, before the instruction stream is executed by the reference and RHDL.

Another test compares 864 instruction/state combinations covering PCs 0/254/255,
wait counters 0/1/2/65535, pin values 0/0x55/0xff, running/halted states, and twelve
valid or malformed instruction words. Native RHDL execution is checked against
the reference. Upstream's pinned, internal
`test_kernel_vm_and_verilog_synchronous` helper then checks RHIF and RTL
interpreters, emitted RTL Verilog, and optimized-netlist Verilog in Icarus.
The comparisons are finite functional tests, not exhaustive state-space proof.

## Actual register bank

The integration harness exports `Processor`, including its RHDL DFF state bank,
and instantiates it with asynchronous-read instruction memory in a Verilog
testbench. Icarus executes 1,454 checked rising edges. Scenarios cover:

- Four-byte UART streams (`00 ff 55 a5`), pins 0/7, bit periods 1/2/8.
- Synchronous reset, including recovery from an active long WAIT.
- Invalid opcode, WAIT(0), reserved SET_PINS bits, and malformed HALT.
- Valid HALT at PC=255 and fault instead of wrap on an incrementing instruction.
- Stable state following halt or fault.

For every edge the testbench checks PC, wait counter, output values, halted and
fault against the independent reference. Simulator failures and missing success
markers cause test failure. Reset is checked independently against zero state.

## Host-side checks

The ISA test round-trips all 65,535 legal WAIT values and all 65,536 mask/value
pairs (with canonical masked values), and rejects malformed words and invalid
program construction. Compiler tests check the twelve-byte limit with WAITs,
the twenty-five-byte limit without WAITs, and an empty payload. CLI tests check
the 43-word `Hi` image at eight clocks per bit and reject invalid pins, zero
period, and overflowed period values. A compile-fail doctest requires Rust to
reject addition between `b8` and `b4`.

## Rust frontend checks

`tests/frontend.rs` compares native Rust effects, captured effect IR, and
reference instruction execution for helper composition, local mutation, `if`
and `match` specialization. A long-wait test checks zero-wait removal, wait merging
and splitting, and retained redundant drives across 80,003 waveform cycles.
Work-limit and native-capture cleanup tests cover bounded compilation, nested
capture rejection and recovery after a native panic.

Macro unit tests require specific diagnostics for unsupported syntax. Compiler
doctests exercise a complete annotated pulse, reject unbounded loops, and require
Rust to reject a non-boolean drive value. The existing RHDL width mismatch
doctest remains. CLI tests also check a deterministic 43-line assembly listing.
The timed frontend retains its existing instruction and cycle behavior. The
untimed frontend adds the bit-operation instructions described below.

`make emit` produces `build/protocol_processor.v`. `make example` produces
`build/uart.mem`. These artifacts are generated rather than checked in.

## Untimed bit logic

The six `bitlogic/tests/logic.rs` integration tests compare ordinary native Rust,
IR evaluation, independent mathematical expectations, and programs executing on
the reference processor. Three-bit operands exhaust all eleven binary operations;
other cases cover mutation, defaults, statement/value conditionals, else-if,
bounded loops, slices, concatenation, shifts, boolean outputs, composition,
explicit pin mappings, and preservation of unmapped output bits. Errors cover
mapping conflicts, invalid widths/values/names, and processor width limits.

Icarus checks 128 combinations of a conditional transform against an independent
Verilog oracle. A separate operator test checks 2,725 cases across 1/3/64-bit
operations, slices, concatenation, and shift boundaries. These tests execute the
emitted combinational HDL, not an alternate handwritten implementation alone.

A clocked processor test runs the captured transform for all 128 input tuples,
checks 3,328 rising-edge observations, and changes physical inputs after capture.
Final pin values agree with the independent oracle. Native RHDL state, including
scratch bits, is also compared with the integer reference at each step.

An additional processor-kernel regression checks 240 cases: all sixteen two-input
truth tables at every Boolean input combination with low/high/aliased destination
registers, capture/write instructions, reserved-bit faults, PC=255, waiting, and
halted states. The pinned RHIF/RTL interpreters and both generated Verilog forms
in Icarus agree with the independent reference. ISA tests round-trip bit operands
and reject out-of-range typed operands and reserved encodings.

Macro rejection tests and four bitlogic compile-fail examples check incomplete
outputs, reads before definition, width and slice mistakes, unsupported syntax,
expansion bounds, input writes, and Rust E0499/E0502 aliasing errors. One additional
bitlogic doctest executes native evaluation and graph/HDL construction. See the
[language and integration guide](bitlogic.md) for the supported subset and limits.

## Limits

There is no formal equivalence proof, post-synthesis regression, FPGA or ASIC
place-and-route result, board test, CDC integration, or electrical verification.
Only Icarus has been exercised for the new processor. A complete program-memory
or loading design has not been implemented. The GitHub workflow is configured
to repeat local checks; no remote CI execution is claimed.
