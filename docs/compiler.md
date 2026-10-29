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
writes `<component.name>.v`, `interface.json`, `report.json`, `ast.txt`, `model.py`,
and `graph.html`. The AST
file shows the full unrolled constructor structure with four-space indentation,
including input/output names, constants, widths, and operation parameters. Shared
expressions are repeated in full at every use; there are no node labels,
references, depth limits, or omitted subtrees. This view describes dependencies;
it does not change expression sharing in the generated hardware. Unrolling can
produce a much larger file than the shared graph. These artifacts
can instead be omitted by passing `--stdout` in place of `--output DIR`, which
prints only generated Verilog to standard output. The two options are mutually
exclusive; compilation diagnostics go to standard error. Generated artifacts
contain no timestamps or machine-specific paths. Reports include compiler
version, ordered ports, node IDs, kinds, widths, parameters, dependencies,
operation counts, fanout (operand edges and output uses), shared IDs, output
bindings, and warnings. They describe the unoptimized graph, not physical cost.
`build/` is ignored. The Tiny Tapeout demo is checked into `src/combhdl_demo.v`;
all consumer workflows check freshness.

`emit_python(component) -> str` emits the same standalone Python model as the CLI.
It validates the in-memory graph directly and leaves `CompileResult` unchanged.
Each reachable non-input node has one straight-line assignment, in identity-based
postorder, named `_combhdl_value_<index>` with the report's node index. Both
branches are computed before selection. Sharing spans all outputs; distinct
equivalent nodes remain separate. All operations retain unsigned fixed-width
semantics, including intermediate arithmetic wrapping and integer `0`/`1`
comparisons. Shifts at least as wide as their operand emit zero.

The function takes all declared inputs in their original order as required
keyword-only `int` parameters, including unused inputs, and returns an ordered
dictionary with the original output names. Boolean, non-integer, negative, and
out-of-range inputs raise `ValueError`; missing, positional, and unexpected
arguments raise Python's normal `TypeError`. Constant-only models take no arguments.
The function uses the component name unless it is invalid in Python, a keyword,
or a built-in name, in which case it uses `_combhdl_model`. Input names with those
same conflicts (including `$`) become `_combhdl_input_<port-index>`. Indices are
zero-based; the module docstring records the component name and parameter aliases.
Output dictionary keys do not need aliases.

Generated Python has no `combhdl` dependency, uses four-space indentation and a
trailing newline, and contains no timestamps. It is a functional debugging model:
sequential assignments do not represent hardware timing or concurrency. Original
construction helpers, loops, and local names are not recovered; `ast.txt` remains
the fully expanded, label-free view.

## Interactive HTML graph

Every `--output DIR` invocation writes `DIR/graph.html`. Open it directly in a
browser: no server, internet connection, JavaScript libraries, or extra Python
dependencies are required. For example, the checksum command produces
`build/ipv4_checksum/graph.html`. The public API `emit_html(component) -> str`
returns the same self-contained report and rejects invalid graphs with
`CompileError`. `CompileResult` and Verilog-only `--stdout` are unchanged.

The diagram is a **directed acyclic graph**: arrows run from producers to their
consumers, from inputs at the top to output ports at the bottom. Valid combhdl
graphs cannot contain cycles. Every reachable expression appears once, including
constants and zero-extensions. Shared expressions have multiple outgoing
connections; equivalent but separately constructed expressions remain distinct.
Unused declared inputs appear as isolated nodes. Output ports have their own
nodes, including outputs bound directly to inputs.

- Select a node, or focus it and press Enter/Space, to inspect its width and
  Python assignment. Arithmetic masks match `model.py`.
- Blue edges trace all upstream dependencies and immediate consumers. Use the
  inspector's producer/consumer buttons to follow individual connections.
- Search by input/output name, operation, report ID (`n26`), or Python temporary
  (`_combhdl_value_26`), then select a matching node to bring it into view.
- Scroll or drag the background to pan. Use the zoom buttons or Ctrl + wheel;
  **Fit graph** shows the whole diagram and **100%** restores readable scale.
- Edge labels preserve operand order: `a`/`b` for binary operations,
  `condition`/`true`/`false` for selection, and destination bit ranges for
  concatenation. Repeated uses of the same operand retain separate edges.

Node IDs match `report.json`; operation variables match `model.py`. The graph
does not recover Python construction-local variable names or show signal values
for a particular input. It describes data dependencies, not hardware timing,
physical routing, or Python execution time. The layered layout can require
scrolling and zooming for large graphs. Without JavaScript, the complete static
SVG and tooltips remain available, with browser scrolling.

Generation is deterministic and iterative, including for a 5,000-operation
chain. The HTML embeds all SVG, CSS, interaction code, and graph data. Original
names are escaped for HTML and embedded JSON is inert.

## Loop example

[`examples/combinational/loops.py`](../examples/combinational/loops.py) constructs
two paths from an eight-bit `value` input:

- `fixed_three`: a Python `for` loop creates three consecutive additions of one.
- `bounded_count`: a second `for` loop creates three conditional stages. A two-bit
  runtime `count` selects how many increments contribute, from zero to three.

```sh
uv run --locked python -m combhdl examples/combinational/loops.py \
  --component component --output build/loops
```

Open `build/loops/graph.html` and search for either output. Selecting `fixed_three`
highlights the simple addition chain. Selecting `bounded_count` also highlights
the three comparisons and `If` nodes; their false edges bypass increments. The
constant one is shared across both paths. All 18 expression nodes and the two
output nodes remain visible, with 29 operand/output connections.

The generated model can be called from the repository root:

```python
from build.loops.model import loop_example

assert loop_example(value=10, count=2) == {"fixed_three": 13, "bounded_count": 12}
assert loop_example(value=255, count=1) == {"fixed_three": 2, "bounded_count": 0}
```

Both Python loops execute at construction time. The graph contains all stages,
and each arithmetic result wraps to eight bits. Input-controlled selection
provides a bounded combinational equivalent of a runtime loop; it does not change
the hardware's size or execute iterations over clock cycles. Unbounded loops and
clocked state feedback remain unsupported.

## Scope and verification

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
