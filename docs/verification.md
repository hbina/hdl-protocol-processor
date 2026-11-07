# Bitlogic verification

Validated locally on 2026-11-07 with rustc 1.99.0
`b940084d7 2026-09-28`, Cargo 1.99.0 `5f94df478 2026-08-27`,
and Icarus Verilog 12.0. Cargo.lock fixes the Rust dependency versions.

```sh
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
make emit example
```

The active workspace has eight tests and five doctests (four compile-fail).

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

The protocol ISA, processor, timed frontend, and processor backend have been
removed, along with their tests. Historical processor/waveform results are not
active bitlogic coverage. See [project history](history.md).

There is no formal equivalence proof, post-synthesis regression, FPGA or ASIC
place-and-route result, board test, CDC integration, or electrical verification.
Only Icarus has been exercised for the emitted HDL. These finite functional tests
do not establish correctness for every possible source program.
