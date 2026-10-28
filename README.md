# Pure Combinational HDL Compiler

Python constructs immutable unsigned expression graphs; `combhdl` validates them,
evaluates them, and emits combinational Verilog. There is no processor, firmware,
clock, storage, or target-side execution sequence. Reusing an expression object
preserves explicit sharing. Separate equivalent expressions remain separate.

**Last updated: 2026-10-29.** Compiler, evaluator, CLI, generated Tiny Tapeout demo,
both simulators, and generic synthesis pass. Physical implementation remains
**blocked**: the installed LibreLane environment has no compatible container
engine. No routed timing, ASIC area, DRC/LVS, mapped-netlist, or FPGA-bitstream
result has been established for this design.

```python
from combhdl import Component, If, Input, Output, Xor, compile

a, b = Input("a", 8), Input("b", 8)
choose = Input("choose", 1)
shared = Xor(a, b)
component = Component(
    "example", [a, b, choose], [Output("result", If(choose, shared, a))]
)
verilog = compile(component).verilog
```

Supported operations: `And`, `Or`, `Xor`, `BitNot`, `Not`, `Eq`, `Lt`, `If`,
`Add`, `Sub`, `Bit`, `Slice`, `Concat`, `Shl`, `Shr`, `ZeroExtend`, `Truncate`.
Widths are positive integers without an eight-bit limit. Constants are explicit,
comparisons are unsigned, and arithmetic wraps to the operand width. See the
[language/API contract](docs/compiler.md) for rules and diagnostics.

| Protocol | Status | Current scope |
|---|---|---|
| UART, SPI, I²C | Not started | Temporal protocols require state, which this language excludes |
| USB, Ethernet, JTAG, SWD, PS/2, CAN | Not started | No implementations in the new architecture |

Verification for the retired processor does not establish protocol support here.

| Check | Current evidence |
|---|---|
| Python language, validation, CLI and integration | `uv run --locked pytest`: 46 passed; includes a 5,000-operation graph, cross-process reproducibility, metadata and Tcl constraint checks |
| All operations in Icarus 12.0 and Verilator 5.038 | `tools.check_simulation`: 8 exhaustive width-one vectors, 512 exhaustive four-bit vectors, 328 boundary/fixed-seed 17-bit vectors, and a constant-only circuit per simulator; independent oracle and evaluator agree |
| Tiny Tapeout wrapper in both simulators | `make -B -C test` and `SIM=verilator`: all 512 meaningful inputs × 12 unused-control patterns = 6,144 checks each |
| Generic Yosys 0.70 synthesis | `tools.check_synthesis`: wrapper 16 cells; operation circuits at widths 1/4/17: 16/79/386 cells; structural checks pass, zero storage and combinational loops |
| Strict Pyright / Ruff | Strict compiler/example/tool checks and formatting pass |
| Tiny Tapeout configuration | Support-tool configuration generation passes; CMOS5L 6×4, clock metadata zero, CTS disabled, virtual 20 ns I/O reference |
| Routed/mapped ASIC verification | Blocked before synthesis: `No compatible container engine found.` |

Exact commands, versions, and source hashes are in
[verification.json](docs/verification.json). Graph counts and generic cell counts
are not LUT usage, physical area, timing, or fit evidence.

```sh
uv sync --locked
uv run --locked pytest
uv run --locked pyright
uv run --locked ruff format --check .
uv run --locked python -m combhdl examples/combinational/shared_logic.py \
  --component component --output build/shared_logic
uv run --locked python -m tools.check_generated
uv run --locked python -m tools.check_simulation --sim icarus
uv run --locked python -m tools.check_simulation --sim verilator
uv run --locked make -B -C test
uv run --locked make -B -C test SIM=verilator
uv run --locked python -m tools.check_synthesis --yosys .venv/bin/yowasp-yosys
uv run ruff format .
```

Icarus, Tcl, a C++ toolchain, and Verilator ≥5.036 are external prerequisites.
CI builds Verilator 5.038. With the existing local build, use
`--executable .asic-tools/verilator/bin/verilator` for `check_simulation`, or
`VERILATOR_BIN_DIR="$PWD/.asic-tools/verilator/bin"` for `make`.
Yosys is a development dependency via `yowasp-yosys`; native Yosys is also
supported with `--yosys yosys`. Python tools use the root uv project.
The [physical-flow guide](docs/physical_flow.md) explains the separate existing
LibreLane environment and remaining constraints/signoff work.

- [x] Define and validate immutable expressions and components.
- [x] Implement iterative traversal, cycle rejection, evaluator, and Verilog backend.
- [x] Verify every initial operation and explicit sharing.
- [x] Provide deterministic CLI artifacts and structured reports/warnings.
- [x] Exhaustively verify the Tiny Tapeout combinational demo in both simulators.
- [x] Integrate generic synthesis, no-storage checks, and active workflows.
- [x] Retire processor RTL, firmware, ISA tooling, loaders, and active regressions.
- [ ] Update and validate the development-container recipe for pinned CMOS5L.
- [ ] Restore the container environment and run the new physical flow.
- [ ] Verify a newly generated mapped netlist, all-corner timing, fit, DRC/LVS.
- [ ] Complete remaining physical signoff, board validation, and power/IR analysis.

No constant folding, algebraic simplification, or structural deduplication is
performed by this compiler. Downstream synthesis can optimize or duplicate logic.
Signed arithmetic, storage, feedback, runtime indexing, hierarchy, tri-states,
and four-state semantics are unsupported. Simulation settling intervals do not
establish physical delay or glitch behavior. The 20 ns virtual timing reference
is a proposed budget, not measured performance. KLayout DRC/XOR remain disabled;
positive future timing alone will not constitute complete signoff.

`combhdl/` contains the compiler; `examples/combinational/` contains construction
examples; `src/` contains checked-in generated HDL, wrapper, and physical config;
`test/compiler/` and `test/demo.py` contain active checks. Old reports are clearly
marked in [docs/history/](docs/history/README.md). Processor sources are recoverable
at **`d3886c6a364637cd736de369a004ac2693e559e2`**; see
[source recovery](docs/source_history.md).

The existing development-container recipe still targets an older PDK/toolchain;
it is not a validated replacement for the pinned CMOS5L physical environment.
