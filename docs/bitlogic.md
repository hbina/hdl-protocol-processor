# Pure structured bit logic in Rust

Bitlogic captures a restricted Rust function as a typed expression graph. The
function maps an owned input value to a complete output value: `F: S1 -> S2`.
The graph can be interpreted, composed with another graph, or emitted as
combinational Verilog. Source functions and locals are immutable. There are no
clock, reset, wait or sampling primitives in the language.

```rust
use bitlogic::{logic, bits, Bits, LogicValue};

#[derive(Clone, Copy, LogicValue)]
struct Inputs { a: Bits<3>, b: Bits<3>, enabled: bool }
#[derive(Clone, Copy, Debug, PartialEq, Eq, LogicValue)]
struct Outputs { value: Bits<3>, different: bool }

#[logic]
fn select(input: Inputs) -> Outputs {
    let combined = input.a ^ input.b;
    Outputs {
        value: if input.enabled { combined + bits::<3>(1) } else { input.a },
        different: input.a != input.b,
    }
}

let input = Inputs { a: bits(2), b: bits(3), enabled: true };
let native = select(input);
let ir = select::ir()?;
let interpreted: Outputs = ir.evaluate_typed(input)?;
assert_eq!(native, interpreted);
let verilog = ir.to_verilog("select_logic")?;
```

The macro retains the original function and supplies a same-named marker type
with `select::ir()`. Rust checks native expressions and field types. Generated
paths expect the crate name `bitlogic`. The function macro does not inspect type
definitions in other files: `LogicValue` derives provide schemas and native value
adapters through ordinary Rust trait resolution. No global registry is used.

## Values and complete results

Leaves are `bool` and unsigned `Bits<N>`, widths 1 through 64. Named non-generic
structs derive `LogicValue` and may nest other derived structs. Deriving `Copy`
and `Clone` is useful for native expression reuse. Leaf and struct values can be
inputs or outputs; the input and output types need not be the same. Group multiple
logical inputs into one struct.

`bits::<N>(value)` masks its literal to N bits. Addition/subtraction wrap at N bits
in every build profile. Comparisons are unsigned; shifts that shift all bits out
return zero, including shift counts >=64. `bool` and `Bits<1>` have different
logical types despite equal physical widths. Conditionals select corresponding
leaves and require the same logical type on both branches.

Each immutable local names an expression value. Immutable shadowing is supported:
a new binding refers to a new expression; it does not mutate the prior value.
Every returned struct literal must provide every field exactly once. Fields may
be written in any source order and support shorthand; schema order follows the
struct declaration. Returning an existing aggregate or selecting complete
aggregates is legal. There are no implicit holds or default output definitions:
return an input field explicitly to preserve it.

A state machine is a pure next-state function. Its input struct can contain
current state, external inputs and instruction/control values; its output is a
complete next-state struct. The surrounding HDL module owns registers, reset,
clock domains, synchronization, validity and pads. Calling the function twice
composes transformations; it does not introduce two hardware cycles.

## Supported Rust subset

- Ordinary non-generic functions with exactly one named owned input and an explicit
  owned output type. Both types must implement `LogicValue`.
- Initialized immutable `let` bindings, optional value type annotations, immutable
  shadowing, nested value blocks and a trailing expression.
- Named field access and complete named struct construction, including qualified
  type paths and shorthand fields.
- `if`/`else if`/`else` expressions, including whole-struct selection.
- Bitwise `&`, `|`, `^`, `!`; `+`, `-`; `==`, `!=`, `<`, `<=`, `>`, `>=`.
- Boolean `&&`, `||`; expressions in this subset have no side effects.
- Literal `<<`/`>>` counts, boolean literals, `bits::<N>(integer literal)`.
- `value.bit(index)`, `value.slice::<N>(offset)`, and
  `high.concat::<LowWidth, TotalWidth>(low)`, with literal indices and widths.
- Explicit bounded immutable folds as described below.

Mutation, references, assignment statements, compound assignments, early returns,
struct-update syntax, destructuring, tuples/arrays/enums, arbitrary helper calls,
ordinary loops, async/unsafe functions, and arbitrary leaf types are unsupported.
`LogicValue` derives require nonempty named non-generic structs. Rust names are
resolved normally for schemas; recognized DSL operations such as `bits` are
syntactic and must use the supplied definitions rather than shadowed substitutes.
Some errors (including dynamic schema validation, flattening name collisions and
invalid bit-method bounds) are reported by `ir()`, while syntax errors and native
Rust type/field errors are compile-time diagnostics.

## Bounded immutable folds

`LogicValue::fold` expresses a pure recurrence and is the only supported closure
form. The method takes one literal count and `|acc, index| expression`:

```rust
#[logic]
fn repeated(input: Bits<8>) -> Bits<8> {
    input.fold::<4>(|acc, index| acc + index)
}
```

The index is `Bits<8>`, ranging from zero through count minus one. The closure
returns the accumulator's logical type and may capture immutable outer values.
Count zero returns the initial accumulator; its body must still use supported
syntax. At most 256 iterations and 65,536 total lowering steps are allowed.
Folds expand into acyclic expressions; they do not synthesize iterative engines,
registers or elapsed time. Struct accumulators support decoder expansion without
mutable locals; the set and processor examples use this form.

## Schemas, evaluation and dependencies

`LogicValue::schema()` retains nested field names, nominal Rust type identity,
and distinct logical leaf kinds. `flatten()` visits fields depth-first in
struct-declaration order. `from_values()` reconstructs the native value, rejecting
wrong counts and out-of-width values rather than silently truncating them.

`Logic::schemas()` exposes input/output schemas. `evaluate_typed::<I,O>(input)`
checks both declared schemas, evaluates the scalar graph, and reconstructs `O`.
`evaluate(&[u64])` remains available and follows schema leaf order. Low-level
`Builder` graphs use port insertion order and do not carry aggregate schemas
unless explicitly attached and checked through `with_schemas()`.

`nodes()`, `inputs()` and `outputs()` expose the expression DAG. `NodeId::index()`
indexes nodes. Every node references earlier nodes; storage and feedback are
absent. `dependencies()` returns each output field path and its contributing input
field paths in input order, including conditional predicates. Dependencies are
structural, not minimal Boolean support: `x ^ x` still reports `x`.

## Composition

`first.then(&second)` requires equal intermediate nominal type and full schema
for structured graphs. Equal leaf widths or coincidentally equal field names
alone are insufficient. Composition preserves the outer input and output schemas.
A dedicated pure adapter function expresses deliberate rewiring between types.
An identity function `fn identity(value: State) -> State { value }` composes on
either side without changing values. Grouping composition does not change values.
No composition adds a register or clock cycle.

Two low-level unstructured graphs can still compose by port count and width.
Mixing structured and unstructured interfaces is rejected; an explicit schema
attachment is required. Runtime `TypeId` identifies nominal types inside one Rust
program; the schema is not a portable persisted ABI or a serialized type identity.

The NetKAT inspiration remains a small compositional language with explicit
semantics. Bitlogic does not implement NetKAT packet history, union, Kleene star
or its complete equational decision procedure. Pure state functions do not need
a state monad: state is explicit in their input and output values.

## HDL integration

Ports use `i_`/`o_` prefixes. A nested path `state.counter` becomes `i_state_counter`
or `o_state_counter`. Struct roots omit the Rust argument name; a scalar input
uses its argument name, and a scalar output uses `result`. One-bit ports use
`[0:0]`. Flattening collisions such as `a_b` and `a.b` are errors. Raw Rust field
identifiers lose the `r#` prefix before HDL naming. All names are validated.

`rename_ports()` provides a checked, order-preserving external HDL adapter;
logical schemas and dependency paths remain unchanged. The processor uses it to
preserve its existing wrapper ABI while accepting a nested `StepInput` in Rust.
Intermediate nodes are continuous-assignment wires, with no inferred registers.
Electrical pad modes, voltage domains and clock-domain safety remain external.

## Bounded set example

```sh
cargo run --locked -p bitlogic --example set
```

`set_step(SetInput) -> SetOutput` represents keys `0..=7` with `Bits<8>`:

| Field | Meaning |
|---|---|
| Input `current` | Current membership bitmap |
| Input `key` | `Bits<3>` key |
| Input `operation` | `Bits<2>`: contains=0, insert=1, remove=2, clear=3 |
| Output `next` | Complete next membership bitmap |
| Output `present` | Key membership in the current bitmap, including during clear |

The immutable decoder fold selects the key's mask. Inserting existing keys or
removing absent keys preserves membership. Every key/operation bit pattern is
valid. Caller-owned storage is unchanged; this is not dynamically allocated
storage or an arbitrary-key collection. Two tests compare native/IR and Icarus
against a `BTreeSet` oracle for all 8,192 input combinations.

## Verification and migration

[Verification](verification.md) records the independent native/IR/HDL tests,
structured composition/dependency checks, diagnostics and processor regressions.
The [migration contract and audit](pure_functions.md) records the baseline and
implementation gates. The mutation-based frontend has been retired. Earlier RHDL
processor results are separately historical; see [project history](history.md).
Functional checks do not establish FPGA fit, electrical correctness or ASIC signoff.

All runnable examples generate HDL and diagrams without arguments; see the
[artifact guide](example_artifacts.md) for files and temporary-folder behavior.
