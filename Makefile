.PHONY: test check emit example processor-synth processor-mapped-test processor-sky130 processor-sky130-test

test:
	cargo test --workspace --locked

check:
	cargo fmt --all --check
	cargo clippy --workspace --all-targets --locked -- -D warnings

emit:
	mkdir -p build
	cargo run --locked -p bitlogic --example emit -- verilog > build/select_logic.v

example:
	cargo run --locked -p bitlogic --example emit -- verilog

processor-synth:
	mkdir -p build
	cargo run --locked -p bitlogic --example protocol_processor -- verilog > build/protocol_processor.v
	UV_CACHE_DIR=$(CURDIR)/build/uv-cache uv run --locked yowasp-yosys -s scripts/processor_synth.ys -l build/processor_synth.log

processor-mapped-test: processor-synth
	BITLOGIC_PROCESSOR_NETLIST=$(CURDIR)/build/protocol_processor_mapped.v cargo test --locked -p bitlogic --example protocol_processor

processor-sky130:
	bash scripts/sky130_flow.sh run

processor-sky130-test: processor-sky130
	bash scripts/sky130_flow.sh models
	bash scripts/sky130_flow.sh audit
	BITLOGIC_PROCESSOR_CLOCKED_NETLIST=$(CURDIR)/build/sky130hd/orfs/results/sky130hd/bitlogic_processor/base/6_final.v BITLOGIC_PROCESSOR_CELL_MODELS=$(CURDIR)/build/sky130hd/sky130hd_cells.v cargo test --locked -p bitlogic --example protocol_processor -- --nocapture > build/sky130hd/postroute_tests.log
	cat build/sky130hd/postroute_tests.log
	uv run --locked python scripts/sky130_report.py
