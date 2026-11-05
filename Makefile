.PHONY: test check emit example

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
