# RHDL Protocol Processor

**Last updated: 2026-10-31.** The previous Python DSL, protocol studies,
Tiny Tapeout integration, and physical-flow tooling have been removed to start
an RHDL protocol processor and a Rust protocol-to-instruction compiler.

This reset stage contains no active implementation, build, or verification flow.
All protocols are **Not started** in this stage. Previous functional and physical
results do not validate the replacement design.

- [x] Remove the legacy project and its build/CI flows.
- [ ] Add the Rust workspace, processor, protocol compiler, and verification.
- [ ] Add Rust and HDL continuous integration.

The previous committed tree is available at
`bd94857315fcb1038f4e4df8f9ac3ca477c2e0c2`. Uncommitted pre-reset source was
also saved at `/tmp/jane-street-before-rhdl-reset-20261030/sources.tar.gz`,
with a diff and status record alongside it. That temporary backup is not durable
Git history.
