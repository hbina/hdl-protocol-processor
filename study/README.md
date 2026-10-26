# Historical studies — previous architecture

These experiments target the superseded request/queue processor and experimental
ISA variants. They are preserved at their original paths with their recorded
successes, failures, and evidence. They are excluded from active CI and may no
longer import or run with the current tools. They establish no coverage for the
pin-driven processor. No compatibility layer or frozen toolchain is provided.

The last pre-refactor source tree is the parent of the `refactor/pin-driven-core`
branch. The separate `bookkeeping/study-refactor-snapshot` branch preserves the
paused study-framework refactor and is not part of this architecture.

See `docs/pin_processor.md` for the active design and `firmware/README.md` for
small standalone examples.
