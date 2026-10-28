# Combinational HDL demonstration

## How it works

Python constructs a pure expression graph and the compiler emits combinational
Verilog. The demo shares `a ^ b` between an output and both selection branches:

- `shared = a ^ b`
- `result = choose ? (shared & a) : (shared | b)`

`ui_in[3:0]` is `a`, `ui_in[7:4]` is `b`, and `uio_in[0]` is `choose`.
`uo_out[3:0]` is `result`; `uo_out[7:4]` is `shared`.
`uio_out` and `uio_oe` are zero. All uio pads are inputs. `uio_in[7:1]`,
`clk`, `rst_n`, and `ena` do not affect outputs. There is no functional clock.

## How to test

```sh
uv sync --locked
uv run --locked pytest
uv run --locked python -m tools.check_generated
uv run --locked make -B -C test
uv run --locked make -B -C test SIM=verilator
```

The wrapper regression exhausts all 512 meaningful inputs and varies unused
inputs independently. See [compiler documentation](compiler.md) and the
[physical-flow guide](physical_flow.md). The virtual 20 ns constraint is a target;
physical implementation and mapped-netlist verification remain incomplete.

## External hardware

No external hardware is required for simulation. On a board, apply static digital
inputs and read the two output nibbles after settling. Board validation remains
open. Outputs may glitch when inputs change.
