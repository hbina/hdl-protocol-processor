> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# CAN active-flag bit-error firmware compaction

2026-10-25. The retained1,076-word integration has been compacted to exactly
**1,024 words** using existing generic instructions. No RTL, opcode or data RAM
is added. The first listing's capacity failure and the frozen1,023-word image's
REC1-versus9/TEC8-versus16 failures remain preserved in the
[earlier investigation](can_flag_bit_study.md).

## Firmware changes

The [builder](../study/protocol_exploration/build_can_flag_compact.py) imports
the frozen oversized draft and creates a separate
[candidate](../study/protocol_exploration/can_flag_compact_candidate.asm).
It recovers52 words without dropping operations1–6 or the earlier counter rules:

| Transformation | Words recovered |
|---|---:|
| Shared boot/recovery counter-clear leaf |8 |
| Shared RX/TX/retry frame-state initialization |21 |
| Three rotates replace five shifts of the isolated three-bit identifier value |2 |
| Remove offline CRC branch padding |2 |
| Remove overwritten scratch calculations |2 |
| Reuse saturating REC+8 leaf for post-flag dominance |1 |
| Shared balanced counter paths and delay fall-through |7 |
| Shared initial11-bit idle qualification |9 |
| Total |52 |

All protocol work remains instruction-driven. Calls are non-nested, as required
by the existing generic one-level link register. Counter clearing, frame setup
and idle qualification occur outside a frame; call/return overhead does not
change the400-clock wire loops. Offline CRC preparation has no on-wire deadline.
The shared REC+8 leaf replaces eight saturating+1 calls with a direct saturating
addition and padding of the same wire-cycle cost.

The original error is counted before sampling its flag. A recessive observation
while commanding an active flag adds8 to the appropriate counter and restarts
flag signaling at the following bit. It does not add another receiver+1. The
new flag's active/passive state uses the counters before that bit error's+8,
preserving threshold-crossing active signaling. Dominance during a passive
flag remains exempt. Passive missing-ACK counting is deferred until the flag
finishes and charges only if it observed dominance, preserving the exception.
The existing64-sample overall flag budget is retained across restarts.

The fault path uses byte252 to save the flag sample budget across generic leaf
calls. This is existing TX packer scratch: the packed-data count is dead after
an abort, retries use the retained expanded frame and saved payload, and a new
frame build rewrites it. It is outside RX state242–249, REC250, TEC251/255 and
the retained TX endpoint253. No new RAM address is allocated.

## Verification

The [extended peer](../study/protocol_exploration/can_flag_compact_peer.py) uses
the earlier independent transceiver-fault model. A forced recessive RXD bit
represents a transceiver/receive-path fault despite dominant TXD; other samples
use the public wired-dominant resolution. Counts are queried through operation6,
without private counter writes. Expected flag commands and transitions come
from a wire-level oracle. An internal observer records only sample times.

```sh
uv run --locked pytest -q test/test_can_flag_compact_units.py
uv run --locked python study/protocol_exploration/run_can_flag_restart.py can_flag_restart --expanded-model
uv run --locked python study/protocol_exploration/run_can_flag_compact.py can_flag_compact --expanded-model --suite postflag
uv run --locked python study/protocol_exploration/run_can_flag_restart.py can_flag_restart --expanded-model --suite rx_flags --test-filter 'test_receiver_error_flags|test_compact_pack_unpack_and_phase'
# Expected production size failure:
uv run --locked python study/protocol_exploration/run_can_flag_restart.py can_flag_restart
```

The extended suite checks all six RX/TX fault positions, subsequent good traffic,
passive dominance, repeated RX faults through a passive transition, an original
RX error crossing127→128, and TX120→128 followed by a passive restart. Sample
timing is checked independently of expected counter/data values. The earlier
post-flag suite exercises prolonged dominant runs, passive ACK exceptions,
REC saturation, bus-off/recovery, winner/retry traffic and selected drift/step
cases. A selected RX-flag regression checks immediate/deferred flags and
pack/unpack/phase behavior; filtered-out groups are not claimed as rerun.

The first compact run reached the later good-RX check but exposed a missing
receive-sample observer in the new fault harness. The observer was enabled;
the old-image comparison was rerun and retained the same two counter failures
and passing passive control. No firmware change was needed for that harness fix.

The [source-bound evidence](can_flag_compact_results.json) records five fault
groups, five post-flag groups, two selected RX groups (three skipped by filter),
all55 project unit tests, exact commands/XML/source hashes and timing artifacts.
Three restart rows contain58 samples at exactly400 clocks apart.

## Remaining limits

Zero model words remain. Production still rejects1,024>128; this is an isolated
1024×18/eight-register CALL model, not mapped ASIC support. No physical flow or
hardware interoperability result is added. Earlier physical source hashes and
signoff risks remain unchanged.

This experiment covers selected error-flag behavior, not overload-flag
generation or complete CAN confinement. Co-occurring/late-form accounting,
full SJW/TX synchronization, legal EOF/intermission/overload handling,
continuous busy-bus service, request/reset coverage and longer disturbed-bus
monitoring remain open. The bounded loop's timeout/after-bus-off precedence and
earlier arbitration-stuff/recovery-timeout integration gaps remain documented.

The full nine-protocol acceptance goal remains open; see the
[acceptance audit](protocol_acceptance_audit.md).
