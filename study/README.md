# Retired study source

The old protocol_exploration tree, predecessor chains, RTL-patching runners and
associated tests/artifacts have been removed. They targeted the superseded runtime
and experimental ISAs and were already excluded from active verification.

Historical findings and JSON evidence remain in docs. Source is recoverable from
commit `c1b6dfc`; the old runtime architecture as a whole is at `efa3001`.
See [Git recovery instructions](../docs/source_history.md) and the
[typed-construction audit](../docs/typed_instruction_audit.md).

The separate `bookkeeping/study-refactor-snapshot` branch preserves the paused
framework refactor. It is not part of the current design.

Use the [current architecture](../docs/pin_processor.md) and
[standalone firmware](../firmware/README.md) for active development.
