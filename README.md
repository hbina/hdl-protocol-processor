# Pure Combinational HDL Compiler

Python constructs immutable unsigned expression graphs; `combhdl` validates them,
evaluates them, and emits combinational Verilog. There is no processor, firmware,
clock, storage, or target-side execution sequence. Reusing an expression object
preserves explicit sharing. Separate equivalent expressions remain separate.

**Last updated: 2026-10-29.** Compiler, evaluator, CLI, generated Tiny Tapeout demo,
both simulators, and generic synthesis pass. Rootless Podman 4.9.3 is now working
and the pinned LibreLane image is installed. The corrected CMOS5L 6×4 flow and
6,144-check mapped regression pass, with positive extracted timing at all three
corners and zero configured routing DRC, Magic DRC, and LVS errors. Physical
signoff remains incomplete: KLayout DRC/XOR, board validation, and realistic
power/IR analysis remain open. No FPGA bitstream result has been established.

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

The [larger checksum example](docs/checksum.md) generates and checks a fixed
20-byte IPv4 header checksum from a 160-bit input. Its Python helpers construct
an adder tree and share a sum between both outputs. It is a combinational
primitive; packet parsing, options, streaming, and protocol state are excluded.

| Protocol | Status | Current scope |
|---|---|---|
| UART, SPI, I²C | Not started | Temporal protocols require state, which this language excludes |
| USB, Ethernet, JTAG, SWD, PS/2, CAN | Not started | No implementations in the new architecture |

Verification for the retired processor does not establish protocol support here.

| Check | Current evidence |
|---|---|
| Python language, validation, CLI and integration | `uv run --locked pytest`: 56 passed; includes checksum/carry tests, a 5,000-operation graph, cross-process reproducibility, metadata and Tcl constraint checks |
| All operations in Icarus 12.0 and Verilator 5.038 | `tools.check_simulation`: 8 exhaustive width-one vectors, 512 exhaustive four-bit vectors, 328 boundary/fixed-seed 17-bit vectors, and a constant-only circuit per simulator; independent oracle and evaluator agree |
| Tiny Tapeout wrapper in both simulators | `make -B -C test` and `SIM=verilator`: all 512 meaningful inputs × 12 unused-control patterns = 6,144 checks each |
| Larger checksum circuit in both simulators | `tools.check_checksum`: 2,508 vectors each, independent byte-oriented oracle, known values, carry boundaries, valid headers and single-bit corruption; [evidence](docs/checksum_results.json) |
| Generic Yosys 0.70 synthesis | `tools.check_synthesis`: wrapper 16 cells; operation circuits at widths 1/4/17: 16/79/386 cells; checksum 1,019 cells; structural checks pass, zero storage and combinational loops |
| Strict Pyright / Ruff | Strict compiler/example/tool checks and formatting pass |
| Tiny Tapeout configuration | Support-tool configuration generation passes; CMOS5L 6×4, clock metadata zero, CTS disabled, virtual 20 ns I/O reference |
| Routed/mapped ASIC verification | `runs/combhdl_demo_02`: 6×4 fit, 53 non-filler cells, 627.782 µm² cell area, 0.06957% utilization; 6,144 mapped observations pass; routing DRC / Magic DRC / LVS: 0 / 0 / 0 |
| Extracted input-to-output timing | All three PVT corners pass at a virtual 20 ns reference; worst setup +17.4318 ns, hold +0.1391 ns; no slew, capacitance, or fanout violations; [physical evidence](docs/physical_results.json) |

Exact commands, versions, and source hashes are in
[verification.json](docs/verification.json) and the linked physical/checksum records. Graph counts and generic cell counts
are not LUT usage, physical area, timing, or fit evidence.

```sh
uv sync --locked
uv run --locked pytest
uv run --locked pyright
uv run --locked ruff format --check .
uv run --locked python -m combhdl examples/combinational/shared_logic.py \
  --component component --output build/shared_logic
uv run --locked python -m combhdl examples/combinational/ipv4_checksum.py --stdout
uv run --locked python -m tools.check_generated
uv run --locked python -m tools.check_simulation --sim icarus
uv run --locked python -m tools.check_simulation --sim verilator
uv run --locked python -m tools.check_checksum --sim icarus
uv run --locked python -m tools.check_checksum --sim verilator
uv run --locked make -B -C test
uv run --locked make -B -C test SIM=verilator
uv run --locked python -m tools.check_synthesis --yosys .venv/bin/yowasp-yosys
uv run ruff format .
```

Icarus, Tcl, a C++ toolchain, and Verilator ≥5.036 are external prerequisites.
Use `--stdout` instead of `--output` to print only the generated Verilog for
inspection or piping. This mode does not create artifact files.
Validated against file-mode checksum HDL with captured stdout/stderr; conflicting
destinations and invalid components fail with diagnostics on stderr.
CI builds Verilator 5.038. With the existing local build, use
`--executable .asic-tools/verilator/bin/verilator` for `check_simulation`, or
`VERILATOR_BIN_DIR="$PWD/.asic-tools/verilator/bin"` for `make`.
Yosys is a development dependency via `yowasp-yosys`; native Yosys is also
supported with `--yosys yosys`. All Python tools, including LibreLane and Tiny
Tapeout orchestration, use this repository's `.venv` through `uv run --locked`.
`uv sync --locked` installs the pinned dependencies; no separate physical-tool
virtual environment is used. See the [physical-flow guide](docs/physical_flow.md)
for container prerequisites and remaining constraints/signoff work.

- [x] Define and validate immutable expressions and components.
- [x] Implement iterative traversal, cycle rejection, evaluator, and Verilog backend.
- [x] Verify every initial operation and explicit sharing.
- [x] Provide deterministic CLI artifacts and structured reports/warnings.
- [x] Exhaustively verify the Tiny Tapeout combinational demo in both simulators.
- [x] Integrate generic synthesis, no-storage checks, and active workflows.
- [x] Retire processor RTL, firmware, ISA tooling, loaders, and active regressions.
- [x] Add a useful larger checksum circuit with helper reuse, shared logic, two-simulator coverage and measured synthesis.
- [ ] Update and validate the development-container recipe for pinned CMOS5L.
- [x] Restore a compatible container environment (rootless Podman 4.9.3).
- [x] Complete the new physical flow and record the resulting artifacts.
- [x] Verify a newly generated mapped netlist, all-corner timing, fit, configured DRC/LVS.
- [ ] Complete remaining physical signoff, board validation, and power/IR analysis.

No constant folding, algebraic simplification, or structural deduplication is
performed by this compiler. Downstream synthesis can optimize or duplicate logic.
Signed arithmetic, storage, feedback, runtime indexing, hierarchy, tri-states,
and four-state semantics are unsupported. Simulation settling intervals do not
establish physical delay or glitch behavior. The 20 ns virtual reference is an
I/O timing constraint; extracted timing results apply to the recorded driving,
load, corner, uncertainty, and derating assumptions. KLayout DRC/XOR remain
disabled; positive timing alone does not constitute complete signoff.

`combhdl/` contains the compiler; `examples/combinational/` contains construction
examples; `src/` contains checked-in generated HDL, wrapper, and physical config;
`test/compiler/` and `test/demo.py` contain active checks. Old reports are clearly
marked in [docs/history/](docs/history/README.md). Processor sources are recoverable
at **`d3886c6a364637cd736de369a004ac2693e559e2`**; see
[source recovery](docs/source_history.md).

The existing development-container recipe still targets an older PDK/toolchain;
it is not a validated replacement for the pinned CMOS5L physical environment.
