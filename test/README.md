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
models; see [physical-flow instructions](../docs/physical_flow.md). No new mapped
netlist is currently available. Processor-specific active tests were retired.
