# Bitlogic

**Last updated: 2026-11-09.** An untimed Rust DSL for bit-vector transformations.
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
cargo run --locked -p bitlogic --example protocol_processor -- demo Hi 0 8
cargo run --locked -p bitlogic --example protocol_processor -- verilog
make check
make emit
```

Optional generic synthesis and mapped-netlist regression use uv with checked-in
`pyproject.toml`/`uv.lock`: `uv sync --locked`, then `make processor-mapped-test`.
See the [synthesis baseline](docs/processor_synthesis.md) for tool versions and scope.
The optional [SKY130 HD block study](docs/sky130_implementation.md) uses rootless
Podman: `make processor-sky130-test` reproduces routing, timing, constraint checks
and routed-netlist functional regression with a pinned tool image.

`make emit` writes `build/select_logic.v`. The generated module has `i_` input
ports, `o_` output ports, and continuous wire assignments. It has no clocks or
inferred registers. See the [language and integration guide](docs/bitlogic.md).

The [set example](crates/bitlogic/examples/set.rs) implements contains, insert,
remove, and clear for keys `0..=7` using an eight-bit membership bitmap. The demo
owns the state; emitted HDL exposes current-state and next-state ports. See the
[set interface](docs/bitlogic.md#bounded-set-example) for operation encodings.

The [protocol processor example](crates/bitlogic/examples/protocol_processor/main.rs)
uses the library for an instruction-driven next-state function. A separate top
module owns registers and synchronous reset. It runs UART TX/RX, a bounded input
poll, SPI, I²C, JTAG sequences, SWD and PS/2 device transmission within documented limits.
See the [architecture](docs/protocol_processor.md),
[protocol scope](docs/protocols.md), and the [step-by-step implementation plan](docs/protocol_processor_plan.md#step-by-step-execution-guide).

## Source layout

| Crate | Responsibility |
|---|---|
| [`bitlogic`](crates/bitlogic/src/lib.rs) | Fixed-width values, typed IR, interpretation, composition, and combinational Verilog |
| [`bitlogic-macros`](crates/bitlogic-macros/src/lib.rs) | Rust assignment/conditional capture and complete-output validation |

Low-level graphs now support explicit structured `Schema` interfaces,
`LogicValue` flattening/reconstruction, typed evaluation, nominal composition,
external port renaming and structural dependency inspection. The existing
mutable frontend remains available at this stage; schemas can be supplied
through `Logic::with_schemas`. Existing scalar graph behavior is preserved.

## Status

| Feature | Status | Evidence/scope |
|---|---|---|
| Rust frontend | Partial | Documented Rust subset; native evaluation retained; repeated assignments, local mutation, conditionals, and bounded loop expansion checked |
| Bit-vector IR and composition | Verified | Independent truth tables, all eleven three-bit binary operations, composition identities, port-shape/value errors, and width boundaries in integration tests |
| Combinational Verilog | Partial | Icarus checks 128 conditional-transform combinations and 2,725 operator/boundary cases; no synthesis or board evidence |
| Ownership and output definitions | Verified | Macro diagnostics plus compile-fail examples for incomplete outputs, input mutation, and Rust E0499/E0502 aliasing errors |
| Bounded set example | Verified | Native Rust, IR, and Icarus match a `BTreeSet` oracle for all 8,192 state/key/operation combinations; eight-key universe, caller-owned storage |
| Protocol processor example | Partial | Checked 32-bit ISA; 327,190 transitions match reference/native/IR and source/generic-mapped HDL; 1,060,580 clocked observations also pass on routed SKY130 cells; chip/IO integration remains |
| UART | Partial | 8N1 TX: 6,144 byte/pin/period cases; 797 single-frame and 780 complete adjacent-frame batch RX scenarios; independent waveforms and clocked HDL; bounded 1..=6-frame reception, no FIFO or board evidence |
| SPI | Partial | 2,112 single-byte full-duplex programs cover four modes, both bit orders, and an independent peer in native/IR/clocked HDL; no multi-byte API or board timing evidence |
| I²C | Partial | 684 single-byte read/write scenarios with an independent resolved-bus peer: all bytes/ordinary addresses, ACK/NACK, busy, stretching and timeout boundaries; reset releases pads; no multi-controller or electrical evidence |
| JTAG | Partial | 672 TAP scenarios plus IR-then-DR sequences from all 16 states; results retained and selected IR survives DR capture; 4-bit IR + 32-bit DR fits 251 words; no device/chain or board integration |
| PS/2 | Partial | 272 resolved-bus device-TX scenarios: all bytes, odd parity, initial inhibit, mid-frame abort and request detection; no host-command receive, automatic resend or physical timing evidence |
| SWD | Partial | 549 independent resolved-wire scenarios: raw 32-bit DP/AP read/write, ACKs, parity, turnaround and bounded WAIT retries; line reset; no target connection or board validation |
| Protocol composition | Partial | Explicit success exits, branch relocation, conservative pin claims and shared-pin release; 24 independent UART/SPI waveforms and conditional-error tests; caller owns scratch/entry contracts |
| CAN, USB, Ethernet | Not started | [Feasibility study](docs/protocol_feasibility.md) selects roles and buffered/controller boundaries; no link implementations |
| Generic synthesis | Verified | Yosys 0.70: 2,527 generic logic cells + 122 flops; structural check and complete mapped processor regression pass; no technology area/timing claim |
| SKY130 HD block implementation | Partial | TT/25 °C/1.8 V routed GDS; 16,205.5 µm² non-filler cell area, +10.0603 ns setup / +0.255771 ns hold slack at a 20 ns target; router DRC/antenna zero and constraint/routed functional checks pass; no chip signoff |

`cargo test --workspace --locked`: **33 tests and 5 doctests pass** (4 compile-fail).
`cargo fmt --all --check`, Clippy with warnings denied, and `make emit example`
pass locally. CI runs the same Rust and HDL checks; no remote execution is claimed.
Exact scope is in [verification](docs/verification.md).

All ten implementation-plan stages have scoped evidence in the
[completion audit](docs/processor_plan_audit.md), including a fresh source,
mapped and routed regression and all 16 documented processor commands.

- [x] Establish an independent bitlogic workspace with locked dependencies.
- [x] Capture ordinary Rust assignments into typed bit-vector expressions.
- [x] Preserve native Rust evaluation and borrowing checks.
- [x] Validate complete output definitions and supported syntax.
- [x] Interpret and compose typed expression graphs.
- [x] Generate and functionally verify combinational HDL.
- [x] Implement and exhaustively verify a bounded set example.
- [x] Retire protocol crates and the processor backend from the active tree.
- [x] Document the [processor and protocol implementation plan](docs/protocol_processor_plan.md) using bitlogic as a library.
- [x] Implement a processor example with checked ISA, independent cycle model, and clocked HDL verification.
- [x] Implement and verify UART transmission on the example processor.
- [x] Add input/scratch operations, runtime branches, bounded loops and timeout polling.
- [x] Add single-byte SPI transfers and single-frame UART reception with independent peer/waveform tests.
- [x] Add bidirectional output controls and resolved-pad I²C read/write verification.
- [x] Add bounded JTAG scans and PS/2 device transmit with independent peer checks.
- [x] Add SWD request/response, parity, turnaround and bounded retries.
- [x] Receive complete adjacent UART frames in bounded batches and preserve JTAG IR/DR sequencing.
- [x] Compose operations with explicit successful exits, pin handoff and independent timing/result checks.
- [x] Study CAN, USB and Ethernet feasibility and record controller/buffering decisions.
- [x] Measure generic synthesis and rerun the processor regression on mapped HDL.
- [x] Select SKY130 HD, define block memory/IO/clock constraints, and verify a routed TT-corner implementation study.
- [ ] Extend the supported Rust subset and composition ergonomics.
- [ ] Add stronger equivalence checking and optimization passes.
- [ ] Complete full-corner timing, chip-level IO/ROM/CDC integration, independent DRC/LVS, power/signoff and hardware validation.

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

There is no library processor backend or RHDL dependency. The processor example
has at most 256 words of externally supplied combinational instruction memory,
eight input/output values and enables, 64 scratch bits and one loop counter. It
has no loader, interrupts, synchronizers or target-specific pad integration. The
logical tri-state pad example is not a physical IO implementation. Reset releases
outputs; HALT and processor fault preserve enables. Open-drain protocol cleanup
releases owned pins, including on modeled error paths.
Protocol rates require an instruction/synchronizer/peer timing budget; logical
simulation does not prove pad timing. UART RX captures at most six frames;
SPI and I²C transfer one byte. JTAG sequences preserve TAP state within the image;
PS/2 needs a stable qualified idle interval and returns inhibited frames to its
caller. SWD assumes an already selected/configured target. Composition requires
explicit success metadata and scratch/entry-state planning. See [protocol limits](docs/protocols.md).
Generic and routed functional regressions are finite evidence. The SKY130 result
is a core-only TT-corner study with explicit external ROM/IO assumptions, not
whole-chip or multi-corner timing closure. Flow checkpoint comparison passes
between mapped netlists; native Rust/IR-to-HDL formal proof is still absent.
No FPGA fit, foundry-deck DRC/LVS, activity-based power/IR/EM signoff, board test
or manufactured hardware validation is claimed. The recorded vectorless power
estimate and tool-model warnings are scoped in the physical study.

## History

The earlier RHDL protocol processor and protocol compiler were committed separately
before retirement. Their code and verification remain in Git history; see
[project history](docs/history.md). Earlier processor results do not verify the
active bitlogic implementation or the new processor example.
