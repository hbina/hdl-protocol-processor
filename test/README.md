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

The default suite runs the five baseline integration groups.

Study evidence below is historical unless explicitly described as a fresh check; matching saved XML/generated model artifacts are required for provenance audits.

See each linked study for exact commands, filters and expected-negative comparisons. Production results and expanded-model results are separate.
