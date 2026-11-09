# Processor synthesis baseline

Measured locally on 2026-11-08. This is target-neutral logic mapping, not FPGA
fit, ASIC area, physical timing, electrical integration or signoff.
The pure structured-function processor migration was rerun through this flow;
all 25 mapped processor tests pass with unchanged coverage. The previous
2,527-cell result is retained in `evidence/2026-11-08/generic_synthesis.json`.

## Reproduce

Rust and Icarus are required for functional tests. Optional synthesis tools are
managed by uv through `pyproject.toml` and `uv.lock`. The locked environment was
run with CPython 3.14.7, YoWASP Yosys package 0.70.0.0.post1259 (Yosys 0.70,
git `28ba3cb92`), yowasp-runtime 1.96 and wasmtime 47.0.1.

```sh
uv sync --locked
make processor-synth
make processor-mapped-test
```

The first command installs the optional environment; no Python package is built
from this repository. `make processor-synth` emits HDL and executes the checked-in
[Yosys script](../scripts/processor_synth.ys). Generated artifacts under `build/`
are ignored: source HDL, tool log, JSON statistics, mapped JSON and mapped Verilog.
The Make target keeps its uv cache under `build/`.

`processor-mapped-test` synthesizes, then selects that netlist through the explicit
`BITLOGIC_PROCESSOR_NETLIST` test setting. The processor tests still compare native
Rust and IR against independent expectations; their HDL paths instantiate the
mapped core/wrapper instead of emitting the source module. A missing or invalid
selected netlist fails the tests. The logical pad model remains outside synthesis.

## Measured results

| Measurement | Result |
|---|---|
| Combinational processor_step | 2,165 generic logic cells |
| State registers | 122 generic synchronous-reset flip-flops |
| Design primitives | 2,287, excluding the hierarchy instance |
| Inferred memory | None; instruction storage is external |
| Longest combinational topological path | 22 mapped cells inside processor_step |
| Structural check | `check -assert` passes |

Cell types are generic AND/OR/NAND/NOR, inverted variants, muxes, XOR/XNOR and
inverters; the flops are `$_SDFF_PP0_`. These are not standard-cell gate
equivalents, micrometres squared, LUTs or routed resources. `ltp -noff` reports a
topological path, not delay or a physical critical path. External ROM, pads,
synchronizers and loads are absent from these counts. Register total matches
the 122 explicit state bits.

Yosys reports one limited-tri-state-support warning while reading `protocol_pads`.
That module is removed as unused under the selected `protocol_processor` top;
mapped tests reattach the original pad model. No tri-state cell synthesis claim
follows from this flow. Resolved-wire simulation remains distinct evidence.

## Selected physical study and remaining integration

The [SKY130 HD block study](sky130_implementation.md) now selects a concrete
platform, 20 ns clock and external-interface assumptions, and completes routing,
extracted TT timing and routed functional regression. Generic mapping remains
separate evidence. A chip-level integration must still implement and validate:

- Instruction storage: a stable combinational ROM interface, or an explicitly
  redesigned synchronous fetch pipeline and its revised protocol cycle contracts.
- Execution clock, reset distribution, test access, startup and IO-safe states.
- Input synchronization/filtering latency and per-protocol sampling budgets.
- IO cells, voltages, open-drain/push-pull modes, loads and external components.
- Technology library/device, implementation constraints, resource budget and
  protocol-specific timing/board checks.

The block study does not close these system-level integration tasks. Independent
ASIC DRC/LVS/signoff and hardware checks remain separately tracked; passing
functional, generic-mapped or single-corner routed checks cannot substitute for them.
