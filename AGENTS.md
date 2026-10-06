# Repository instructions for coding agents

These instructions apply to the entire repository.

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
