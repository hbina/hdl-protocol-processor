# Repository instructions for coding agents

These instructions apply to the entire repository.

## Rust and hardware verification

This is a Rust workspace with an RHDL protocol processor and host-side protocol
implementations that compile to its instructions. Use Cargo for Rust dependencies
and keep `Cargo.lock` checked in. Pin RHDL dependencies to explicit Git revisions.
Run `cargo fmt --all`, `cargo clippy --workspace --all-targets --locked -- -D warnings`,
and `cargo test --workspace --locked` for material Rust changes. Icarus Verilog
(`iverilog` and `vvp`) is required by hardware integration tests.

Keep the instruction encoding, Rust reference model, RHDL decoder, and cycle
contract in sync. Protocol compiler tests must check emitted programs against
independent expected behavior and the clocked generated HDL where appropriate.
Do not claim physical timing, FPGA fit, or ASIC signoff from functional simulation.

## Optional Python tooling

Use `uv` to manage Python environments and dependencies for this project.
Run Python scripts and tools with `uv run`, install the locked dependencies with
`uv sync --locked`, and use `uv add` or `uv remove` to change dependencies.
Keep `pyproject.toml` and `uv.lock` in sync when dependencies change.

If Python tooling is introduced, use Ruff to format it:

```sh
uv run ruff format .
```

## Keep the README status current

After every material project change, update the root `README.md` in the same
change so that it remains the authoritative, concise progress dashboard.

A material change includes:

- implementing, extending, or removing a protocol or architectural feature;
- adding, removing, or changing verification coverage;
- changing synthesis, place-and-route, timing, area, DRC, LVS, or power results;
- changing the supported toolchain, installation procedure, or build commands;
- discovering or resolving a limitation, blocker, or signoff risk; and
- completing, adding, reprioritizing, or abandoning a tracked milestone.

When updating the README:

1. Update the `Last updated` date when the status itself changes.
2. Keep the protocol matrix honest. Use `Not started`, `Partial`, or `Verified`
   only when the corresponding evidence supports that label.
3. Record the exact test or physical-flow evidence for claims of completion.
4. Update the roadmap checkboxes and the limitations/signoff section.
5. Keep detailed design material in `docs/` and link to it from the README;
   do not turn the progress dashboard into a second design specification.
6. Do not delete prior limitations merely because a new test passes. Remove or
   revise a limitation only when the underlying issue has actually been fixed.

Before finishing a task, check whether the work made any README status stale.
If it did, the task is not complete until the README has been updated.
