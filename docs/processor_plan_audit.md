# Processor plan completion audit

Audited 2026-11-08 against the original ten-stage implementation plan. Completion
here means the scoped library examples and studies specified by that plan. It
does not mean complete protocol standards, a chip tapeout or hardware signoff.

| Stage / requirement | Authoritative evidence |
|---|---|
| 1: widths, ISA/reserved bits, cycle priority, waits, final PC, reset and fetch contract | [Processor contract](protocol_processor.md); `isa.rs`, `core.rs`, wrapper; hand-worked edge table includes WAIT(1/2), HALT and fault boundaries |
| 2: checked pins/waits/image, raw decoding, expected encodings and independent cycle model | `isa.rs`, `reference.rs`, `runner.rs`; `checked_isa_encodings_and_image_limits`, direct state expectations and bounded/infinite-run outcomes |
| 3: supported DSL only, complete next-state definitions, native/IR/reference checks | `#[logic] processor_step`, complete returned `ProcessorState`, 327,190 independent transition vectors including injected boundaries/ignored instructions; no library backend/RHDL dependency |
| 4: generated comb HDL plus clocked registers/reset/ROM, full traces and reset recovery | `processor_top.v`, test ROM fetch by PC, 801 raw-program edges plus pad reset tests; native/IR/source and mapped/routed HDL paths |
| 5: UART TX builder, exact periods including one clock, capacity, empty/multi-byte cases, commands/images/listing | UART builder, 6,144 byte/pin/period programs against serialized-frame oracle, maximum WAIT waveform, acceptance boundaries and historical CLI export checks (now replaced by [artifact generation](example_artifacts.md)) |
| 6: input capture, scratch truth tables and aliases, output-bit preservation, indexing resource cost | Input/scratch transition cases; independent truth-table expectations; bounded decoder implementation and 2,418-node/111,484-byte graph/source measurements; atomic sampling/word parity extensions documented and checked |
| 7: runtime branches/counters, target validation, timeout/result handling, termination limits | ISA JUMP/BRANCH_BIT/LOAD_COUNT/DEC_JUMP; 8,836 polling edges, branch/timeout sweeps, loop limits and structurally checked targets |
| 8 SPI: controller mode/order/select/capture schedule and independent peer | 2,112 programs, four modes/two orders, received results, sample/clock/select waveform checks; rate limits documented |
| 8 UART RX: start/sample timing, phase variation, complete back-to-back reception, framing errors and timeout | 797 single-frame/error cases plus 780 complete two-/six-frame batch scenarios; all byte values and phases at minimum period; later-frame error preserves earlier data |
| 8 I²C: drive/release, START/STOP, ACK/NACK, idle/stretch/timeout, single-controller scope | 684 independent resolved-bus cases plus reset release; all bytes/ordinary addresses, both ACK phases, 19 release points and exact timeout boundaries |
| 8 JTAG: reset/TAP, IR/DR shifting and result/state retention | 672 TAP scenarios plus IR-then-DR from all 16 initial states; selected IR survives into DR capture; 251-word paired image |
| 8 SWD: ownership/turnaround, request/response, parity, WAIT/FAULT and bounds | 549 independent push-pull scenarios, all ACK encodings, retry boundaries and read parity; line-reset/atomic-sample checks; matching-drive overlap also rejected |
| 8 PS/2 selected role: framing, odd parity, inhibit and role-specific exit behavior | 272 resolved-bus device-TX cases; all bytes, initial inhibit, mid-frame abort and pending-host-request detection; host commands/resend and physical idle qualification limits retained |
| 8 CAN/USB/Ethernet: choose role/variant, external boundary, clocks, buffering, throughput and dedicated hardware | [Feasibility study](protocol_feasibility.md), with primary sources, explicit candidate controller/PHY/transceiver choices, resource/clock budgets and acceptance gates; implementation is not claimed |
| 9: shared builder, labels/delays, composition, ownership/handoff, results and timing errors | [Composer contract](protocol_composition.md), 24 independent combined UART/SPI waveforms, conditional success/error exits, all branch relocation kinds, rejected resources/capacity and append rollback |
| 9 optional annotated frontend | Considered and deferred as explicitly optional; no unsupported host/runtime Rust lowering claim is made |
| 10: select target/clock/memory/IO assumptions and measure implementation | SKY130 HD, external combinational ROM and IO budgets in [config/constraints](sky130_implementation.md); technology mapping, placement, CTS, route, extraction and GDS complete |
| 10: appropriate physical/functional checks with honest scope | Extracted TT timing and all-constraint sanity pass; router DRC/antenna zero; checkpoint comparison passes; routed clocked regression checks 1,060,580 observations; raw reports/hashes retained |
| Required project checks and dashboards | Cargo format/Clippy/workspace suite; 39 tests and eleven doctests; locked optional uv tools, Ruff and generic/routed targets; README, verification, protocol limitations and roadmap updated together |

Detailed coverage and exact counts are in [verification](verification.md).

Final revalidation on 2026-11-08 passed formatting, workspace Clippy with warnings
denied, all 39 workspace tests and eleven doctests, and all 25 processor tests on
both the generic mapped and routed netlists. The routed run independently
reported 1,060,580 clocked observations. All 16 processor commands documented in
the architecture guide and `make emit example` succeeded. Freshly emitted RTL
matches the synthesis and physical-flow input files byte for byte; all 15
artifact/configuration/report hashes in the recorded physical summary match
the current files, and the physical report checker and Ruff checks pass.

[Protocol limits](protocols.md) remain binding: bounded storage/images, supported
roles/modes, external synchronizers/pads, stable idle/input assumptions and no
unbounded buffering/concurrent engines. These are explicit architectural limits,
not removed by a passing test.

The physical stage is a block study at one selected corner, as distinguished from
the plan's separately tracked ASIC signoff. Full-chip memory/IO/CDC integration,
full corners, independent foundry DRC/LVS, activity-based power/IR/EM, packaging
and manufactured-hardware/board validation remain future work. No signoff or
unimplemented CAN/USB/Ethernet support is inferred from the completed study.

The 2026-11-09 example update replaces CLI demos/modes with automatic HDL and
diagram artifact export; historical command counts above describe the audit
snapshot, while the protocol builders and independent regression remain active.
