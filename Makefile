.PHONY: test check emit example

test:
	cargo test --workspace --locked

check:
	cargo fmt --all --check
	cargo clippy --workspace --all-targets --locked -- -D warnings

emit:
	mkdir -p build
	cargo run --locked -p protocol-processor --bin export-processor > build/protocol_processor.v

example:
	cargo run --locked -p protocol-compiler -- uart-tx --pin 0 --cycles-per-bit 8 --text Hi --output build/uart.mem
