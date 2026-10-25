# CAN receive-tail firmware compaction

2026-10-25. The retained1,067-word draft now fits exactly **1,024 words** after
43 words of firmware reuse/compaction. The seven receive-tail groups pass,
including the three formerly failing wire cases. Five retained flag-error groups
and two selected RX regressions also pass. This uses the same isolated generic
CALL model; no opcode, RTL or data RAM is added. Production still rejects1,024>128.

The [builder](../study/protocol_exploration/build_can_tail_compact.py) creates a
separate [candidate](../study/protocol_exploration/can_tail_compact_candidate.asm).
The oversized draft and old-image wire failures remain preserved in the
[original tail investigation](can_tail_study.md).

## Measured code changes

| Transformation | Words recovered |
|---|---:|
| Share firmware CRC calculation among RX, offline TX and live TX |25 |
| Decode DLC through an incrementing pointer |3 |
| Preserve output DLC directly in its consumer register |1 |
| Remove an offline CRC staging move |1 |
| Share saturating REC store tails |3 |
| Pass the offline input bit directly to the shared feedback entry |1 |
| Remove unused last-EOF input read |1 |
| Twelve generic delay segments produce the same six-bit overload pulse |1 |
| Remove seven redundant masks with proven register-value invariants |7 |
| Total |43 |

The CRC routine remains ordinary shifts, masks, rotates, XORs and branches in
firmware. It has no protocol-specific opcode or hardware. RX retains the same
CRC-path cycle cost through padding. Live TX moves its CRC state into the leaf's
registers and restores the selected output bit afterward; added work is offset
by shorter waits, preserving the400-clock bit period. Offline TX preparation
may take more clocks. No nested leaf calls are introduced.

`INBIT` changes only register bit0; it **does not clear upper bits**. The removed
masks are safe because their callers establish zero upper bits and subsequent
paths preserve that invariant. Frame initialization now writes address247
before242, returning r0=1 rather than144 to idle qualification. It writes the
same state with the same words/cycles. The unsafe predecessor falsely transmits
on a dominant bus and returns22 instead of busy timeout6. A preserved independent
negative comparison reproduces it; the corrected image rejects the busy request
without driving, then completes good TX without reset/reload.

Recessive idle qualification retains400 clocks per sample. Dominant busy polling
and SOF polling become shorter after mask removal; their local deadlines remain
bounded, but are not claimed as the former exact clock counts. Selected RX
phase/rate and error-flag regressions validate the resulting behavior.

## Receive-tail behavior and scope

- ACK delimiter and first six EOF bits retain form checking. Receiver last-EOF
  polarity is ignored, allowing valid data to be returned when that bit is dominant.
- Dominance in intermission bits1/2 generates a six-dominant-bit overload flag,
  including when the node remains error passive due to TEC128. The overload does
  not charge a receive/transmit error count in the selected clean cases.
- The delimiter waits for eight recessive samples with a32-sample total budget.
  Dominance in its eighth bit triggers a following overload flag. At most two
  flags are generated per captured frame; a third request returns local timeout25.
  Subsequent valid RX works without reset/reload.
- A dominant third intermission bit preserves the completed frame and is treated
  as the next-frame boundary. The current one-frame capture returns its first
  frame while the successor is **unacknowledged**. This is not continuous-node RX.

RX packet storage and runtime operations remain as before. TX tail handling is
unchanged; overload-flag bit-error/prolonged-dominance counters and full delimiter
form-error handling remain absent. A bounded disturbed-bus wait is not complete
CAN error recovery. The third-overload timeout drops the captured frame rather
than returning successful received data; that remains a bounded-service limit.

## Verification and reproduction

The [extended peer](../study/protocol_exploration/can_tail_compact_peer.py) uses
public transceiver pins and runtime counter queries. The expected waveform/data
come from independent frame construction and a wire schedule, not DUT RAM or
instruction traces. Payloads0/1/8, repeated requests, both overload trigger bits,
repeated flags, eighth-delimiter dominance, the local flag cap, passive-node
signaling and recovery after a busy/overload timeout are covered.

```sh
uv run --locked pytest -q test/test_can_tail_compact_units.py
uv run --locked python study/protocol_exploration/run_can_tail_compact.py can_tail_compact --expanded-model
uv run --locked python study/protocol_exploration/run_can_tail_compact.py can_tail_compact --expanded-model --suite flag_errors
uv run --locked python study/protocol_exploration/run_can_tail_compact.py can_tail_compact --expanded-model --suite rx_flags --test-filter 'test_receiver_error_flags|test_compact_pack_unpack_and_phase'
uv run --locked python study/protocol_exploration/run_can_tail_compact.py can_tail_compact --expanded-model --suite postflag --test-filter 'test_receiver_postflag_dominance|test_postflag_threshold_and_saturation|test_transmitter_postflag_counts|test_postflag_bus_off_recovery'
# Expected failure: unsafe idle initialization returns22 instead of6.
uv run --locked python study/protocol_exploration/run_can_tail_compact.py can_tail_compact --expanded-model --unsafe-idle --test-filter test_busy_transmit_qualification
# Expected failure: actual ASIC program capacity.
uv run --locked python study/protocol_exploration/run_can_tail_compact.py can_tail_compact
```

The old post-flag profile group is deliberately excluded: it asserts local17 for
last EOF/intermission, the behavior this change replaces. Its source/results stay
frozen. New tail tests supply the replacement acceptance oracle. The other three
RX groups are also filtered out and are not claimed as rerun.

The [result record](can_tail_compact_results.json) includes a fresh seven-group
receive-tail run with matching source/XML hashes. The five flag-error, two RX
and four selected post-flag groups and the unsafe-idle negative are retained
historical runs: source formatting has changed since those runs, so their
original hashes are preserved without claiming current source integrity.
The pre-commit project unit suite passes all 57 tests. CI runs the positive
suites and retains artifacts; expected-negative runs remain separate.
No new mapped/physical or hardware evidence is claimed.

**Next task goal:** test and attempt TX-tail handling and overload-flag fault
accounting with independent peers. Preserve the current passing image, measure
code/cycle costs and keep all protocol behavior in generic firmware. Full SJW/TX
synchronization, continuous service, request/reset and other acceptance gaps
remain in the [audit](protocol_acceptance_audit.md). Zero model words remain.
