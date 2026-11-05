# Untimed bit logic in Rust

`bitlogic` captures a restricted Rust function as a typed expression graph. The
same graph can be interpreted, emitted as combinational Verilog, or composed with
another graph. Ordinary
assignments define values; no `connect()` calls, clock, reset, wait, or sampling
primitive appears in the source language.

```rust
use bitlogic::{logic, bits, Bits};

#[logic]
pub fn select(a: &Bits<3>, b: &Bits<3>, enabled: &bool, output: &mut Bits<3>) {
    *output = *a;
    if *enabled {
        *output = (*a ^ *b) + bits::<3>(1);
    }
}

let ir = select::ir()?;
assert_eq!(ir.evaluate(&[2, 3, 1])?, [2]);
let verilog = ir.to_verilog("select_logic")?;
```

Run the complete example:

```sh
cargo run --locked -p bitlogic --example emit -- verilog
```

The macro retains the original function, so `select(&a, &b, &enabled, &mut output)`
remains ordinary native Rust. Rust checks its types, mutable access, and borrowing.
The generated same-named marker type provides `select::ir()` without needing
concrete input values. Generated paths expect the crate name `bitlogic`.

## Values, assignments, and ownership

Ports are immutable references for inputs and mutable references for outputs.
They may be `bool` or unsigned `Bits<N>`, with literal widths 1 through 64.
Widths are const generic parameters in the native function and explicit metadata
in the IR. `bits::<N>(value)` masks a literal to N bits. Addition/subtraction
wrap at N bits, including in debug builds. Comparisons are unsigned. Constant
shifts that shift all bits out produce zero, including shift counts >=64.

The frontend converts successive assignments into successive expression values:

```text
*output = *input;          output_1 = input
*output = *output ^ mask;  output_2 = output_1 XOR mask
                          final output = output_2
```

This creates a single final output definition. Assignments do not create clocks
or separate persistent hardware drivers. `if` becomes a multiplexer, and bounded
loops expand into repeated expressions. An output begins undefined in the DSL,
even though the native caller passes an initialized Rust value. Reading it before
assignment, or leaving it undefined on any path, is a macro error. Set a default
before a conditional or assign it in every branch. No latch is inferred.

Shared input references allow fan-out. Mutable references describe exclusive
access during native evaluation. They do not establish a lifetime for physical
drivers or a physical pin identity. The IR has named logical ports; the top module
connects them to actual pins. Public low-level `Builder` construction does not receive
the source macro's Rust borrowing checks.

## Supported Rust subset

- Ordinary, non-generic functions returning unit, with named reference parameters.
- Initialized `let` / `let mut` locals and optional `bool` / `Bits<N>` annotations.
- `*port = expression` and `local = expression`; repeated assignments are legal.
- Bitwise `&`, `|`, `^`, `!`; `+`, `-`; `==`, `!=`, `<`, `<=`, `>`, `>=`.
- Boolean `&&`, `||`; their expressions have no side effects in this subset.
- Literal `<<` / `>>` counts, boolean literals, `bits::<N>(integer literal)`.
- `value.bit(index)`, `value.slice::<N>(offset)`, and
  `high.concat::<LowWidth, TotalWidth>(low)`, all with literal indices/widths.
  Port receivers may use Rust's method autodereference.
- Statement `if` / `else if` / `else`, and value `if` expressions with an `else`.
  Value blocks allow local declarations and a trailing value expression.
- Nested statement blocks and `for _ in start..end` / `start..=end` with literal
  bounds, limited to 256 iterations per loop and 65,536 total lowering steps.

Shadowing, reference aliases inside the body, indexed loop variables, arbitrary
helper calls, compound assignments, early exits, unbounded loops, closures,
macros in bodies, and arbitrary Rust types are rejected. Use the supplied `Bits`
and `bits` definitions; names/types are recognized syntactically, without rustc
name resolution. Expressions and ports reserve no user-visible temporary names:
IR construction temporaries live in a separate generated companion function.

## Graph and composition

`Logic::nodes()`, `inputs()`, and `outputs()` expose the typed graph. A `NodeId`
indexes `nodes()` through `index()`. Operations describe constants, inputs,
bitwise/arithmetic expressions, comparisons, muxes, slices, concatenation, and
shifts. Each node only references earlier nodes; storage and feedback are absent.

`first.then(&second)` wires first's outputs to second's inputs by port order,
requiring equal port counts and widths. This composes value transformations
without introducing time. Input/output arrays to `evaluate()` follow the order
of their respective reference parameters in the source signature. Values outside
the input width are errors, rather than silently truncated.

The NetKAT inspiration is a small compositional language with explicit semantics.
This implementation is deterministic; it does not implement NetKAT packet
filtering, union, history, Kleene star, or a complete equational decision procedure.

## HDL integration

`to_verilog("select_logic")` emits an acyclic combinational module. Ports are named
`i_a`, `i_b`, `i_enabled`, and `o_output`; one-bit ports use `[0:0]`. Intermediate
nodes are wires with continuous assignments. There are no inferred registers.

The user supplies a top module that instantiates this logic and owns registers,
clock domains, synchronizers, reset, enables, input/output validity, bidirectional
pads, and electrical modes. State machines can be represented by explicit
current-state input and next-state output ports; the surrounding module owns the
state register. Rust borrow lifetimes have no clock-domain meaning.

## Verification

`cargo test --workspace --locked` checks native Rust and graph interpretation
against independent mathematical expectations and executes generated combinational
HDL in Icarus. Five integration tests cover small exhaustive truth tables,
composition, all eleven binary operations, one-/three-/64-bit boundaries, slices,
concatenation, and shifts. A macro unit test and four compile-fail examples cover
unsupported syntax, incomplete outputs, width/slice errors, and borrowing errors.
See [verification](verification.md) for exact evidence and commands.

The previous processor backend and its associated tests have been retired. Their
results are historical; see [project history](history.md). The active library
has no processor ISA or RHDL dependencies.

This is functional verification. No FPGA fit, physical timing, ASIC signoff, or
electrical correctness is established.
