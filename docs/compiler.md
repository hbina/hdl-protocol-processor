# Language and compiler contract

Python runs at construction time. A helper returns an expression graph fragment;
it does not create a hardware call. Python loops and containers may construct a
finite graph. No Python parser, bytecode translation, instruction stream, or
scheduling framework is involved.

```python
from combhdl import Const, Eq, If, Not


def ChooseWhenNonzero(value, when_true, when_false):
    return If(Not(Eq(value, Const(0, value.width))), when_true, when_false)
```

`Input(name, width)` and `Const(value, width)` are immutable unsigned expressions.
`Output(name, expression)` infers its width. `Component(name, inputs, outputs)`
copies the ordered collections into tuples. A component may have zero inputs
and must have at least one output. Every expression exposes `.width`. Expression
identity defines sharing; equivalent independent constructions are not merged.

Widths must be positive integers (not booleans). Constants must satisfy
`0 <= value < 2**width`. Integers are never implicitly converted to expressions.
Names follow `[a-zA-Z_][a-zA-Z0-9_$]*`, excluding Verilog/SystemVerilog keywords
and the internal `_combhdl_` prefix. Port names are unique across both directions.
All declared inputs, even unused ones, are validated. Input references must
use the exact declared object; a new Input with the same name is undeclared.

| Constructor | Rule and result |
|---|---|
| `And(a,b)`, `Or(a,b)`, `Xor(a,b)` | Equal-width bitwise operations, same width |
| `BitNot(value)` | Width-masked complement |
| `Not(value)` | One-bit operand and result |
| `Eq(a,b)`, `Lt(a,b)` | Equal-width unsigned operands, one-bit result |
| `If(condition,a,b)` | One-bit condition, equal-width branches; both are validated |
| `Add(a,b)`, `Sub(a,b)` | Equal-width operands, same-width result modulo `2**width` |
| `Bit(value,index)` | Constant index within operand, one-bit result |
| `Slice(value,low,width)` | Bits `low+width-1:low`, all within operand |
| `Concat(a,b,...)` | At least one operand; first contributes most significant bits |
| `Shl(value,amount)`, `Shr(value,amount)` | Constant nonnegative integer amount; width retained; logical shifts; amount ≥ width gives zero |
| `ZeroExtend(value,width)` | High zero bits; destination at least operand width |
| `Truncate(value,width)` | Low bits; destination at most operand width |

Equal-width extension and truncation are legal. Preserve addition carry by
extending both operands first. Extending the result of an eight-bit addition
cannot recover its discarded carry. Expressions reject Python truth conversion;
use `If`, not Python `if expression`.

`compile(component)` returns `CompileResult(verilog, interface, report, warnings)`.
`evaluate(component, inputs={...})` returns output-name/integer pairs. The evaluator
requires exactly all declared inputs, including unused ones, with in-range
unsigned integer values. Constant-only circuits use `inputs={}`. Invalid graphs
raise `CompileError` with component and port/output dependency context. Invalid
constructors fail immediately, before a component exists.

Validation uses iterative identity-based DFS over declared outputs and operand
order. It rejects unsupported types/kinds, undeclared inputs, inconsistent widths,
and cycles; only reachable nodes are emitted. Traversal, evaluation, and emission
do not depend on Python's recursion limit. Unused declared inputs remain ports
and produce structured `unused-input` warnings. No optimization passes run.

Every non-input node, including constants and selection, has one deterministic,
explicit-width wire and continuous assignment. This isolates arithmetic from
context-dependent Verilog sizing. Reusing a node emits it once. The emitter
uses conservative unsigned Verilog with `default_nettype none` and restores
`wire` at the end. There are no procedural blocks, registers, latches, clocks,
resets, memories, initial values, or multiple drivers.

```sh
uv run --locked python -m combhdl examples/combinational/shared_logic.py \
  --component component --output build/shared_logic
uv run --locked python -m tools.check_generated --write
uv run --locked python -m tools.check_generated
```

The CLI executes a **trusted Python file**, selects the exported component, and
writes `<component.name>.v`, `interface.json`, and `report.json`. These artifacts
can instead be omitted by passing `--stdout` in place of `--output DIR`, which
prints only generated Verilog to standard output. The two options are mutually
exclusive; compilation diagnostics go to standard error. Generated artifacts
contain no timestamps or machine-specific paths. Reports include compiler
version, ordered ports, node IDs, kinds, widths, parameters, dependencies,
operation counts, fanout (operand edges and output uses), shared IDs, output
bindings, and warnings. They describe the unoptimized graph, not physical cost.
`build/` is ignored. The Tiny Tapeout demo is checked into `src/combhdl_demo.v`;
all consumer workflows check freshness.

The initial language excludes mutable variables, statements, assignment blocks,
feedback, state, delays, signed/floating arithmetic, multiply/divide/remainder,
runtime indexing, target-side arbitrary calls, HDL module instances, open-drain,
tri-state, bidirectional or four-state logic. Reuse uses Python helpers. Both
branches of an `If` exist as hardware. There is no guarantee of glitch freedom,
propagation delay, or Verilog X/Z equivalence to the two-state evaluator.

Verification exhausts small inputs, checks independent arithmetic expectations,
and compares all outputs in both simulators after settling. Larger cases use
boundaries and seed `20261028`. Yosys `check -assert`, `scc -expect 0`, and a
combinational-cell whitelist reject undriven logic, loops, storage, and unresolved
hierarchy. Synthesis may simplify or duplicate the generated expressions.
