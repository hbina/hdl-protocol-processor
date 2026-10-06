# Sample testbench for a Tiny Tapeout project

This is a sample testbench for a Tiny Tapeout project. It uses [cocotb](https://docs.cocotb.org/en/stable/) to drive the DUT and check the outputs.
See below to get started or for more information, check the [website](https://tinytapeout.com/hdl/testing/).

## Setting up

1. From the repository root, run `uv sync --locked`.
2. Edit [Makefile](Makefile) when adding Verilog source files.
3. Keep [tb.v](tb.v) synchronized with the project's top-level module.

## How to run

To run the RTL simulation:

```sh
uv run make -B -C test
```

Run the command from the repository root. Add `SIM=verilator` to use
Verilator instead of Icarus Verilog.

To run gate-level simulation, first harden your project using the
[physical-flow guide](../docs/physical_flow.md), then copy the final netlist
from the repository root:

```sh
cp runs/wokwi/final/nl/tt_um_protocol_emulator.nl.v test/gate_level_netlist.v
```

With `PDK_ROOT` set as described in that guide, run:

```sh
uv run make -B -C test GATES=yes
```

If you wish to save the waveform in VCD format instead of FST format, edit tb.v to use `$dumpfile("tb.vcd");` and then run:

```sh
make -B FST=
```

This will generate `tb.vcd` instead of `tb.fst`.

## How to view the waveform file

Using GTKWave

```sh
gtkwave tb.fst tb.gtkw
```

Using Surfer

```sh
surfer tb.fst
```
