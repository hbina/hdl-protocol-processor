> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# Recovering retired source

Historical reports and JSON evidence remain in docs. Their source paths may no
longer exist in the working tree. The obsolete code is recoverable from Git;
there is no compatibility layer or bundled old toolchain.

| Version | Contents |
|---|---|
| c1b6dfc | State immediately before typed-builder cleanup: text-based UART generators, archived study tree, retired runtime tests and firmware |
| efa3001 | Pre-pin-v1 architecture and original runtime/experimental ISA, before the direct-pin processor refactor |
| bookkeeping/study-refactor-snapshot | Separate paused study-framework experiment; not part of the active processor |

Inspect a retired source file without modifying the checkout:

```sh
git show c1b6dfc:study/protocol_exploration/build_can_rx.py
git show c1b6dfc:firmware/historical/runtime.asm
git show c1b6dfc:test/test_runtime_units.py
```

Restore source on a separate branch when needed:

```sh
git switch -c inspect-old-study
git restore --source=c1b6dfc -- study/protocol_exploration
```

Restoring archived files does not make them compatible with today's ISA. To inspect
or reproduce the old runtime architecture as a whole, use a separate checkout:

```sh
git worktree add --detach /tmp/protocol-runtime-history efa3001
```

The retained evidence records include original source hashes and commands; use the
matching historical version to audit those results. Do not treat old passing tests,
capacity findings, or mapped results as coverage for the current pin processor.
