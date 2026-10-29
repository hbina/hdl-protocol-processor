# Active verification

`uv run --locked pytest` collects `test/compiler/`: language semantics, invalid
construction and graphs, immutable/shared nodes, deep traversal, evaluator input
validation, deterministic subprocess CLI builds, checked-in HDL freshness,
Tiny Tapeout metadata/configuration, and Tcl constraint syntax/contract.

`tools.check_simulation` tests all supported operations at widths 1, 4, and 17
using independent integer expectations and the evaluator in Icarus and Verilator.
It also verifies a constant-only module. Reports/logs go under ignored `build/`.

`uv run --locked make -B -C test` runs `demo.exhaustive_wrapper`. Use
`SIM=verilator` for the other simulator. The 512 meaningful input combinations
are each checked with 12 patterns: all unused bits low, each unused bit high,
and all high. The ten bits are uio[7:1], clk, rst_n, ena. Outputs and constant uio
drivers must be unchanged. Each observation follows a 1 ns simulation settling
interval, which carries no physical-delay guarantee.

`GATES=yes` selects a newly generated `gate_level_netlist.v` and PDK functional
models; see [physical-flow instructions](../docs/physical_flow.md). The recorded
`combhdl_demo_02` netlist passes all 6,144 observations. Prefer the provenance-aware
`tools.check_mapped` command below. Processor-specific active tests were retired.

`tools.check_checksum --sim icarus` and `--sim verilator` exercise the larger
160-bit checksum example against 2,508 independent oracle vectors per simulator.
The Python suite also checks known values, carry folding, helper validation, and
sharing. The generic synthesis command includes this circuit and rejects storage.

`tools.run_physical --engine podman --run-dir runs/<fresh-name>` records source
snapshots and tool/container provenance before launching the pinned CMOS5L flow.
`tools.check_mapped --run-dir runs/<name>` selects that run's exact final netlist
without overwriting a shared copy, verifies provenance, and runs all 6,144 board
observations. `tools.report_physical --run-dir runs/<name>` audits the real
all-corner reports, saved constraints, DEF allocation, cells, DRC/LVS, and mapped
result before writing a physical evidence record. See the physical-flow guide.
