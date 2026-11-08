.PHONY: test check emit example processor-synth processor-mapped-test

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
