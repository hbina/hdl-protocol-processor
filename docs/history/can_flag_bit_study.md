> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# CAN active error-flag bit errors: reproduced counter gap

2026-10-25. The independent transceiver-fault peer reproduces missing counter
increments in the frozen1,023-word image. RX reports REC1 rather than9; TX
reports TEC8 rather than16. The passive-flag dominance control passes. These
are functional failures, separate from instruction capacity.

The [peer](../study/protocol_exploration/can_flag_bit_peer.py) injects a recessive
RXD observation during one active-flag bit while checking that ASIC TXD still
commands dominant. An ordinary wired-dominant peer cannot create this fault;
the explicit override models a failed/disconnected dominant transceiver driver
or faulty receive path. Other observations use the public resolved pin signals.
The test neither writes private counters nor computes expected counts from
firmware execution. It queries counters through runtime operation6.

The two active tests intend to sweep all six flag positions and then exchange
good traffic. Both currently stop at their first position on the demonstrated
counter mismatch; the remaining positions/recovery are **not** proven. The
control reaches REC136 through eight real faulty receive exchanges, then
checks dominant passive RX/TX flags without an active-flag bit-error charge.

```sh
# Expected failure: two active counter mismatches; one passive control passes.
uv run --locked python study/protocol_exploration/run_can_flag_bit.py can_flag_bit --expanded-model --prior-monitor

# Expected failures: actual capacity limits, before simulation.
uv run --locked python study/protocol_exploration/run_can_flag_bit.py can_flag_bit
uv run --locked python study/protocol_exploration/run_can_flag_bit.py can_flag_bit --expanded-model
uv run --locked pytest -q test/test_can_flag_bit_units.py
```

The [draft builder](../study/protocol_exploration/build_can_flag_bit.py) produces
a retained [1,076-word integration](../study/protocol_exploration/can_flag_bit_candidate.asm).
It moves the initial error charge before flag monitoring, preserves the passive
ACK exception, proposes+8 updates/restarts and reevaluates passive state for a
subsequent flag. It uses generic instructions and existing transmit-packer
scratch252; there is no new ISA, RTL or allocated RAM. **This draft has no
behavioral proof:** the real generic assembler rejects1,076>1,024, and production
rejects1,076>128. Timing pads, scratch lifetime, repeated faults, state transitions
and all previous regressions still require executable verification.

The [saved evidence](can_flag_bit_results.json) contains source/XML fingerprints,
exact negative-test outcomes, both capacity diagnostics and project-unit command.
The unit preserves generated-source freshness and the two size failures; it does
not validate the proposed protocol behavior. The previous positive1,023-word
image and its evidence remain unchanged. No physical flow was rerun.

The [compacted follow-up](can_flag_compact_study.md) now recovers52 words and
passes selected active-flag counter/restart tests and earlier regressions on a
separate1,024-word image. The draft above remains preserved and unverified.

**Follow-up originally required:** recover at least52 instruction words through generic firmware
reuse/compaction, then run the new fault peer and prior CAN regressions. If that
fails, preserve the measured costs and evaluate a reusable encoding/storage
change. Do not count the draft as implemented CAN support or claim a timing
blocker before it can execute.

The full nine-protocol goal remains open. Full CAN timing/EOF/overload/busy-bus
service and other acceptance gaps remain recorded in the
[acceptance audit](protocol_acceptance_audit.md).

Reference: [Bosch CAN2.0](https://tech-tools.com/files/can2spec.pdf), Part A
sections6.1–6.2 and7 rules1,4,5,9: active-flag bit errors add8 to the appropriate
counter; passive-flag dominance is exempt, and threshold-crossing flag behavior
must be preserved. Overload-flag generation remains outside this experiment.
