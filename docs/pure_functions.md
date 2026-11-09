# Pure structured functions: language contract and migration

The replacement frontend describes total combinational functions `F: Input -> Output`.
A function has exactly one owned argument and one explicit return type. Leaves
are `bool` and unsigned `Bits<1..=64>`; named structs derive `LogicValue` and may
contain other derived structs. Struct field order determines depth-first leaf
order. `bool` and `Bits<1>` have different logical types. Native Rust remains
callable. Registers, clocks, reset, CDC and pads remain external.

Implemented form:

```rust
#[derive(Clone, Copy, LogicValue)]
struct State { counter: Bits<8>, enabled: bool }
#[logic]
fn step(current: State) -> State {
    let incremented = current.counter + bits::<8>(1);
    State {
        counter: if current.enabled { incremented } else { current.counter },
        enabled: current.enabled,
    }
}
```

Immutable initialized locals, field projection, complete struct literals, value
blocks and `if`/`else` expressions are supported. Existing unsigned operators,
constant bit/slice/concat operations and constant shifts retain their semantics:
arithmetic wraps at the leaf width and shifts beyond the width return zero.
Every conditional returns the same logical type on both paths; aggregate
conditionals select corresponding leaves. Only the final expression returns.
Mutation, references, early returns, implicit holds, struct-update shorthand,
arbitrary helper calls, loops and unsupported Rust types are rejected.
Explicit bounded `value.fold::<N>(|acc, index| expression)` provides immutable
unrolling (0..=256 iterations, eight-bit index, existing lowering work bound).
No iteration adds registers or elapsed time. No global type registry is used.

Schemas retain nominal Rust type identity, field paths and logical leaf kinds.
HDL names flatten field paths with underscores; collisions must fail rather than
silently shorting ports. Low-level `Builder` remains available for scalar graphs.
Structured composition checks the intermediate nominal type and full schema;
explicit adapter functions perform intentional rewiring. Dependency inspection
reports structural dependencies, including predicates, rather than algebraically
minimal support.

## Migration gates

- [x] Capture baseline and preserve independent reference models.
- [x] Derive structured schemas and native flatten/reconstruct adapters.
- [x] Add structured IR interfaces and immutable expression lowering.
- [x] Verify native/IR/HDL aggregate behavior and dependencies.
- [x] Verify nominal composition and its identities.
- [x] Migrate simple examples, set, then processor without changing cycle semantics.
- [x] Retire mutable frontend and replace diagnostics/documentation.
- [x] Run Rust, source HDL, generic mapped and applicable physical regressions.

Baseline revision: `e4784a926d096a9fb3134eb3e1d08a6f6c4adaf1`.
Before edits, `cargo test --workspace --locked` passed 33 tests and five doctests;
all 25 processor tests passed in 22.58 seconds. Processor capture reported 2,314
nodes and 107,058 Verilog bytes. The pre-migration emitted module is retained
locally in `build/pure-baseline/processor.v`. Existing `docs/evidence/2026-11-08/`
records the pre-migration generic synthesis and SKY130 study. Those historical
measurements remain separate from the freshly revalidated results below.

## Completion audit (2026-11-08)

All ten requested stages are implemented and verified. The old mutation-based
frontend is removed; this is a replacement frontend, not a compatibility wrapper.

| Requested stage | Current evidence |
|---|---|
| 1. Language contract | This specification and [language guide](bitlogic.md): accepted/rejected syntax, wrapping/shift/conditional semantics, explicit state boundary |
| 2. Baseline | [Baseline record](evidence/pure-migration/baseline.json), archived prior physical evidence and Git revision; independent integer reference and HDL wrapper unchanged |
| 3. Structured values | `LogicValue` derive and trait, nominal nested schemas; round trips, declaration order, bool/Bits<1> separation and malformed values in `tests/structured.rs` |
| 4. Structured IR | Input/output schemas, typed evaluation, checked HDL flattening, collision rejection and explicit external port adapters |
| 5. Immutable lowering | Native/IR/Icarus independent aggregate expectations; whole-struct muxes, field shorthand, qualified types, value blocks and immutable shadowing; scalar operator regressions retained |
| 6. Dependencies | Independently specified output/input field paths, conditions, unused-input exclusion and conservative cancellation case; public DAG inspection retained |
| 7. Composition | Nominal/schema rejection, explicit adapters, both identity laws and associativity across all sixteen fixture states |
| 8. Examples and processor | Pure emit/set/processor functions; immutable decoder folds; all set cases and all 25 source/mapped/routed processor tests pass with original cycle/waveform counts |
| 9. Retirement | Mutable frontend lowering removed; macro diagnostic checks and ten compile-fail examples; README and guides replaced |
| 10. Revalidation | Format, Clippy, 39 tests + 11 doctests, 16 processor commands, source/mapped/routed HDL, fresh SKY130 implementation and report/hash audit |

The [validation record](evidence/pure-migration/validation.json) identifies tested
source hashes and exact counts. [Workspace tests](evidence/pure-migration/workspace_tests.log),
[Clippy](evidence/pure-migration/clippy.log),
[mapped tests](evidence/pure-migration/mapped_tests.log),
[routed tests](evidence/pure-migration/routed_tests.log) and
[command exits](evidence/pure-migration/commands.log) preserve the local results.
The physical measurements are in the [fresh summary](evidence/pure-migration/sky130_summary.json).

`bash scripts/processor_migration_equiv.sh` reconstructs and compiles the original
revision in a temporary source directory, emits the current core, hides incidental
node names, and proves all 122 next-state output bits with Yosys. The
[proof log](evidence/pure-migration/processor_equivalence.log) and
[generated Yosys script](evidence/pure-migration/processor_equivalence.ys) preserve
the result. This is a scoped old-HDL/new-HDL transition proof; a general proof of
native Rust/IR/frontend soundness remains future work.

Fresh SKY130 TT results: 15,713.8 µm² non-filler standard-cell area, +10.3544 ns
setup and +0.253807 ns hold slack at the 20 ns target. Router DRC/antenna counts
are zero; constraints and checkpoint comparison pass; 1,060,580 routed clocked
observations pass. Full-corner timing, chip ROM/IO/CDC integration, foundry-deck
DRC/LVS, activity-based power/IR/EM and hardware validation remain unverified.
