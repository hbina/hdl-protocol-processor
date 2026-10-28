# Source recovery

The programmable processor, firmware, ISA/assembler/linker tooling, loaders,
instruction snapshots, and active processor/protocol regressions were retired
when the pure combinational compiler and replacement demo passed verification.

The processor recovery revision is **`d3886c6a364637cd736de369a004ac2693e559e2`**.
Inspect files without changing the current worktree:

```sh
git show d3886c6a364637cd736de369a004ac2693e559e2:src/protocol_core.v
git ls-tree -r --name-only d3886c6a364637cd736de369a004ac2693e559e2
```

[Historical reports](history/README.md), including the
[processor dashboard](history/processor_dashboard.md), retain their evidence for
old architectures. They do not verify combhdl, protocol support, or its physical
implementation. Earlier runtime/study recovery references are preserved in
[the historical index](history/source_history.md). The paused framework refactor
remains on `bookkeeping/study-refactor-snapshot` and is not an active dependency.
