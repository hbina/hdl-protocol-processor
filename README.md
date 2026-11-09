# Bitlogic

**Last updated: 2026-11-09.** An untimed Rust DSL for pure bit-vector
transformations: `F: Input -> Output`. Write immutable expressions and return a
complete struct, capture a typed expression graph, then interpret it or emit
combinational Verilog. The native function remains callable. Clocking, reset,
CDC, state registers and pad integration belong in the user's top module.

```rust
use bitlogic::{logic, bits, Bits, LogicValue};

#[derive(Clone, Copy, LogicValue)]
struct State { counter: Bits<8>, enabled: bool }

#[logic]
fn step(current: State) -> State {
    State {
        counter: if current.enabled { current.counter + bits::<8>(1) }
                 else { current.counter },
        enabled: current.enabled,
    }
}

let input = State { counter: bits(255), enabled: true };
let ir = step::ir().unwrap();
assert_eq!(ir.evaluate_typed::<_, State>(input).unwrap().counter.get(), 0);
let verilog = ir.to_verilog("step").unwrap();
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
| [`bitlogic-macros`](crates/bitlogic-macros/src/lib.rs) | Pure expression capture and structured-value derivation |

The [pure structured-function migration](docs/pure_functions.md) replaces the
mutable frontend. Struct schemas, typed evaluation, dependencies, nominal
composition and all examples are migrated. Source, mapped and freshly routed
regressions pass; a scoped equivalence check proves the processor transition
outputs match the pre-migration HDL.

## Status

| Feature | Status | Evidence/scope |
|---|---|---|
| Rust frontend | Partial | Immutable owned input/output values, nested structs, value conditionals and bounded folds; native/IR/Icarus agreement, documented subset |
| Bit-vector IR and composition | Verified | Independent truth tables, all eleven three-bit binary operations, composition identities, port-shape/value errors, and width boundaries in integration tests |
| Combinational Verilog | Partial | Icarus checks 128 conditional-transform combinations and 2,725 operator/boundary cases; no synthesis or board evidence |
| Pure structured interfaces | Verified | Six structured integration tests, schema round trips, nominal composition laws, dependency expectations, and ten compile-fail examples; complete returned values |
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
| Generic synthesis | Verified | Yosys 0.70: 2,165 generic logic cells + 122 flops; structural check and complete mapped processor regression pass; no technology area/timing claim |
| SKY130 HD block implementation | Partial | Fresh migrated RTL at TT/25 °C/1.8 V: 15,713.8 µm² cell area, +10.3544 ns setup / +0.253807 ns hold slack at 20 ns; router DRC/antenna zero, constraint audit and routed regression pass; no chip signoff |

`cargo test --workspace --locked`: **39 tests and 11 doctests pass** (10 compile-fail).
`cargo fmt --all --check`, Clippy with warnings denied, and `make emit example`
pass locally. CI runs the same Rust and HDL checks; no remote execution is claimed.
Exact scope is in [verification](docs/verification.md).

All ten implementation-plan stages have scoped evidence in the
[completion audit](docs/processor_plan_audit.md), including a fresh source,
mapped and routed regression and all 16 documented processor commands.

- [x] Establish an independent bitlogic workspace with locked dependencies.
- [x] Capture pure Rust expressions and complete structured results into typed graphs.
- [x] Preserve native Rust evaluation and type checks.
- [x] Validate complete returned values and supported immutable syntax.
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
- [x] Replace mutable ports with pure structured functions, derived schemas, typed composition and dependency inspection.
- [ ] Extend the supported Rust subset and composition ergonomics.
- [x] Prove migrated processor next-state HDL equivalent to the pre-migration implementation.
- [ ] Extend formal checking to frontend semantics and add optimization passes.
- [ ] Complete full-corner timing, chip-level IO/ROM/CDC integration, independent DRC/LVS, power/signoff and hardware validation.

## Limits

The frontend supports one owned input and one complete output, with `bool`,
unsigned `Bits<1..=64>` and nested non-generic named structs deriving `LogicValue`.
Mutation, references, arbitrary helpers, early returns, struct-update shorthand,
ordinary loops, arrays/tuples/enums and arbitrary leaf types are unsupported.
Immutable shadowing is allowed. Bounded folds have expansion/work limits.
Arithmetic wraps at the declared width. Some schema and bit-bound errors are
reported by `ir()` rather than during Rust compilation. Structural dependencies
are conservative, and nominal type identities are local to a Rust process.

The IR is acyclic and combinational. State is explicit in input/output structs;
registers belong in the surrounding module. Types do not establish clock-domain
safety, electrical correctness, protocol correctness or efficient hardware.
Physical pin connections remain the top module's responsibility.

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
between mapped netlists. Migration equivalence proves this processor's emitted
next-state outputs against its baseline HDL; a general native Rust/IR-to-HDL
formal proof is still absent.
No FPGA fit, foundry-deck DRC/LVS, activity-based power/IR/EM signoff, board test
or manufactured hardware validation is claimed. The recorded vectorless power
estimate and tool-model warnings are scoped in the physical study.

## History

The earlier RHDL protocol processor and protocol compiler were committed separately
before retirement. Their code and verification remain in Git history; see
[project history](docs/history.md). Earlier processor results do not verify the
active bitlogic implementation or the new processor example.
