# Protocol and runtime verification

Five baseline cocotb tests exercise the real loader/runtime pins: legacy protocols,
ECHO/XOR requests, transport boundaries, ISA/timing, and malformed records/reset
recovery. All tests work against RTL and the mapped netlist without relying on
internal hierarchical signals. The pin controller uses the same ABI library
as a board adapter: [tools/runtime.py](../tools/runtime.py).

Assembler, storage/FIFO, and controller recovery unit tests run separately:

```sh
uv run pytest -q test/test_assembler.py test/test_runtime_units.py test/test_runtime_driver.py
```

Storage tests include simultaneous FIFO operations at depths 1/3/4/64 and
record/output publication/ownership boundaries. See [runtime.md](../docs/runtime.md)
for the implemented interface and limitations.

## Setting up

1. From the repository root, run `uv sync --locked`.
2. Edit [Makefile](Makefile) when adding Verilog source files.
3. Keep [tb.v](tb.v) synchronized with the project's top-level module.

## How to run

To run the RTL simulation:

```sh
uv run make -B -C test
```

The default suite runs the five baseline integration groups plus UART/SPI/JTAG probes (ten tests total).

Study evidence below is historical unless explicitly described as a fresh check; matching saved XML/generated model artifacts are required for provenance audits.

Recorded runtime physical flow: 79.15% utilization, positive setup/hold slack at 50 MHz in three corners, zero routing/Magic DRC and LVS errors, and five mapped integration tests. See [source-bound runtime results](../docs/runtime_results.json) and [physical flow](../docs/physical_flow.md). These are historical 2026-10-07 results.

Production UART/SPI/JTAG valid-request probes exchange arbitrary payloads without firmware reload; images use 107/72/125 words. Recorded Icarus suite: ten passing tests. See [contracts and results](../docs/protocol_probe_results.md).

I2C/SWD/PS2/Ethernet model experiments record 5/2/2/6 passing groups. Their 249/230/188/280-word images exceed production capacity. See [I2C](../docs/i2c_capacity_study.md), [SWD/PS2](../docs/wave_b_results.md), and [Ethernet](../docs/ethernet_capacity_study.md).

See each linked study for exact commands, filters and expected-negative comparisons. Production results and expanded-model results are separate.
