# Bitlogic

**Last updated: 2026-11-07.** An untimed Rust DSL for bit-vector transformations.
Write normal assignments in `#[logic]` functions, capture a typed expression graph,
and interpret it or emit combinational Verilog. The native function remains
callable and Rust checks its types and borrowing. Clocking, reset, CDC, state
registers, and pad integration belong in the user's top module.

```rust
use bitlogic::{logic, bits, Bits};

#[logic]
fn invert(input: &Bits<8>, output: &mut Bits<8>) {
    *output = *input ^ bits::<8>(0xff);
}

let ir = invert::ir().unwrap();
assert_eq!(ir.evaluate(&[0x55]).unwrap(), [0xaa]);
let verilog = ir.to_verilog("invert").unwrap();
```

## Run

Install Rust with edition 2024 support and Icarus Verilog (`iverilog`, `vvp`).
The workspace is tested with rustc/Cargo 1.99.0 and Icarus 12.0; an older minimum
Rust version has not been established. Cargo.lock fixes dependency versions.

```sh
cargo test --workspace --locked
cargo run --locked -p bitlogic --example emit -- verilog
cargo run --locked -p bitlogic --example set -- demo
cargo run --locked -p bitlogic --example set -- verilog
make check
make emit
```

`make emit` writes `build/select_logic.v`. The generated module has `i_` input
ports, `o_` output ports, and continuous wire assignments. It has no clocks or
inferred registers. See the [language and integration guide](docs/bitlogic.md).

The [set example](crates/bitlogic/examples/set.rs) implements contains, insert,
remove, and clear for keys `0..=7` using an eight-bit membership bitmap. The demo
owns the state; emitted HDL exposes current-state and next-state ports. See the
[set interface](docs/bitlogic.md#bounded-set-example) for operation encodings.

## Source layout

| Crate | Responsibility |
|---|---|
| [`bitlogic`](crates/bitlogic/src/lib.rs) | Fixed-width values, typed IR, interpretation, composition, and combinational Verilog |
| [`bitlogic-macros`](crates/bitlogic-macros/src/lib.rs) | Rust assignment/conditional capture and complete-output validation |

## Status

| Feature | Status | Evidence/scope |
|---|---|---|
| Rust frontend | Partial | Documented Rust subset; native evaluation retained; repeated assignments, local mutation, conditionals, and bounded loop expansion checked |
| Bit-vector IR and composition | Verified | Independent truth tables, all eleven three-bit binary operations, composition identities, port-shape/value errors, and width boundaries in integration tests |
| Combinational Verilog | Partial | Icarus checks 128 conditional-transform combinations and 2,725 operator/boundary cases; no synthesis or board evidence |
| Ownership and output definitions | Verified | Macro diagnostics plus compile-fail examples for incomplete outputs, input mutation, and Rust E0499/E0502 aliasing errors |
| Bounded set example | Verified | Native Rust, IR, and Icarus match a `BTreeSet` oracle for all 8,192 state/key/operation combinations; eight-key universe, caller-owned storage |

`cargo test --workspace --locked`: **8 tests and 5 doctests pass** (4 compile-fail).
`cargo fmt --all --check`, Clippy with warnings denied, and `make emit example`
pass locally. CI runs the same Rust and HDL checks; no remote execution is claimed.
Exact scope is in [verification](docs/verification.md).

- [x] Establish an independent bitlogic workspace with locked dependencies.
- [x] Capture ordinary Rust assignments into typed bit-vector expressions.
- [x] Preserve native Rust evaluation and borrowing checks.
- [x] Validate complete output definitions and supported syntax.
- [x] Interpret and compose typed expression graphs.
- [x] Generate and functionally verify combinational HDL.
- [x] Implement and exhaustively verify a bounded set example.
- [x] Retire protocol crates and the processor backend from the active tree.
- [ ] Extend the supported Rust subset and composition ergonomics.
- [ ] Add stronger equivalence checking and optimization passes.
- [ ] Measure synthesis, physical timing, resources, and board behavior.

## Limits

The frontend supports `bool` and unsigned `Bits<1..=64>` in a documented Rust
subset. Arbitrary helpers, type aliases, reference aliases in bodies, shadowing,
compound assignments, unbounded loops, and arbitrary Rust types are unsupported.
Names and types are recognized syntactically. Loops have expansion/work limits.
Arithmetic wraps at the declared width; outputs must be defined on every path.

The IR is acyclic and combinational. State requires explicit current-state input
and next-state output ports with registers in the surrounding module. Types and
borrowing do not establish clock-domain safety, electrical correctness, protocol
correctness, or efficient hardware. Physical pin connections remain the top
module's responsibility.

The set example has a fixed eight-key universe; it does not provide dynamically
allocated storage or arbitrary key types.

There is no processor backend, runtime instruction image, or RHDL dependency in
the active workspace. No formal equivalence proof, FPGA fit, ASIC implementation,
physical timing closure, or hardware signoff is claimed.

## History

The protocol processor and protocol compiler were committed separately before
retirement. Their code and verification remain in Git history; see
[project history](docs/history.md). Earlier processor results do not verify the
active combinational HDL implementation.
