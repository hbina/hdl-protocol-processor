# Project history

Development now focuses on the standalone `bitlogic` and `bitlogic-macros` crates.
The protocol processor, protocol compiler, protocol ISA, protocol macros, and
bitlogic's processor backend were retired from the active tree on 2026-11-05.
The active DSL and HDL backend do not depend on those crates or on RHDL.

The retirement followed two separate commits so the implementations remain
reviewable and recoverable:

- `0e6e0b4c`: protocol input capture and bit-computation instructions, reference
  semantics, RHDL hardware, and their tests. Its workspace passed 12 tests and
  four doctests.
- `9a19b2d3`: the bitlogic frontend, typed IR, interpreter, composition, HDL and
  processor backends. The combined workspace passed 19 tests and nine doctests.

These are historical results. Removing the processor backend also removed its
pin-mapping checks and clocked hardware tests; those are not claims about the
current bitlogic workspace.

## Earlier migration note

Before retirement, a migration to a separate RHDL checkout at `rhdl/` on branch
`feature/protocol-processor` was reported. That note recorded four ported protocol
crates, ten tests, four doctests, formatting, scoped Clippy, Verilog export, and
example generation passing there. Pushing the fork and verifying a fresh remote
clone remained pending. The `rhdl/` directory is absent in this checkout; the
current work and verification apply to the root workspace.

## Pre-reset project

The pre-reset committed tree is available at
`bd94857315fcb1038f4e4df8f9ac3ca477c2e0c2`:

```sh
git show bd94857315fcb1038f4e4df8f9ac3ca477c2e0c2:README.md
```

Uncommitted pre-reset source was additionally saved outside the repository at
`/tmp/jane-street-before-rhdl-reset-20261030/sources.tar.gz`, with a diff and
status record alongside it. This temporary backup is not durable Git history.
