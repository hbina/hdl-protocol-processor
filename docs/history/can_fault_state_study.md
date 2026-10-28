> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# CAN persistent counters and selected fault confinement

2026-10-25. A **1,020-word candidate** adds persistent transmit/receive error
counters, selected active/passive error signaling, bus-off isolation and
firmware-monitored recovery. It reuses the existing generic leaf-call model;
no new RTL, opcode or data memory is added. Four model words remain.
Production still rejects1,020>128. This is not complete CAN fault confinement.

The [corrected builder](../study/protocol_exploration/build_can_fault_equal.py)
extends a preserved [1,016-word prototype](../study/protocol_exploration/build_can_fault.py),
which itself extends the [bounded RX phase/winner/retry firmware](can_resync_study.md).
The [corrected image](../study/protocol_exploration/can_fault_equal_candidate.asm)
uses the existing1024×18/eight-register generic CALL/RET model, without carry
operations. Counters, flag selection, sampling, retries and recovery all execute
as firmware instructions.
Five corrected model groups and all51 project unit tests pass. Exact commands,
source/XML hashes and timing observations are in the [result snapshot](can_fault_state_results.json).

## Persistent state and request contract

RAM250=REC,251=TEC low and255=TEC high persist across requests. Moving request
operation storage into a register frees250;251/255 were previously unused.
No RAM is added, and the existing private128–255 half is now fully occupied.
Boot explicitly clears these bytes. Reset/reload starts a new node instance;
ordinary request completion and counter queries do not reset the counts.

The model remains50 MHz/125 kbit/s, with uio0=TXD and uio1=RXD through an external
CAN transceiver/terminated bus. The transceiver performs no protocol control.
Valid request envelopes remain required; full envelope validation is absent.

| Operation | Behavior |
|---|---|
|1 | Receive a standard frame; return ID/DLC/payload as before |
|2 | One managed TX attempt; missing ACK/selected bit errors now emit a flag and update counters; terminal detail reports1 |
|3 | Managed TX with up to3 total attempts |
|4 | Managed TX with winner reception/ACK, retained-payload retry and up to3 total attempts; up to33 winner-output bytes |
|5 | If bus-off, monitor recovery; otherwise leave counts unchanged and complete |
|6 | Return `[TEC_low, TEC_high, REC]` as3 output bytes, without changing counts |

Operations2–4 use the prior3-byte ID/DLC arguments and DLC0–8 input bytes.
Operation2's error behavior intentionally differs from the older diagnostic
single-attempt image. Operations5/6 use no input or arguments; query output
limit is3. Bus-off rejects protocol requests with status26, drains their actual
input and leaves output enable0. Queries and explicit recovery remain available.
Counter queries expose software RAM through normal FIFO output; they are not
new hardware registers or protocol-specific peripherals.

## Implemented counter and flag rules

- TX ACK/selected bit errors choose a flag using the **pre-error** counter state.
  Thus the error taking TEC120→128 still sends an active flag. The flag begins
  at the next bit boundary after the75% error sample.
- An error-active flag drives six dominant bits. An error-passive flag releases
  TXD and waits for six consecutive sampled bits of equal polarity. Dominant
  observation during that flag is remembered for the passive ACK exception.
- TEC increases by8 for these transmitted error flags, except passive missing
  ACK with no dominant flag sample, and the selected arbitration stuff-bit
  exception. A successful own transmission decreases nonzero TEC by1.
- Selected local RX CRC/stuff/form/ACK-loopback errors increase REC by1, capped
  at255. Unsupported-format status18 and timeout are not counted as those errors.
  Successful reception decreases REC1–127 by1; REC≥128 becomes127, a permitted
  recovery value. **RX error flags are still absent.**
- Either counter≥128 selects passive behavior; both below128 select active.
  TEC≥256 disables protocol output through generic `SETOE 0`. REC saturation
  alone does not cause bus-off.
- Passive internal retries include an eight-bit suspend wait. The wait does not
  switch to receiving new traffic during suspension; full busy-bus behavior is
  not implemented. Inter-request TX also retains the existing idle qualification.

TEC/REC handling is deliberately described by error class. Remaining normative
rules include flag bit errors, prolonged dominant sequences, other error types,
overload behavior and full counter exception coverage. The selected rules do
not justify a claim that all CAN fault-confinement transitions are implemented.

## Bus-off recovery and bounded waits

Operation5 leaves output enable0 while firmware samples every400 clocks. It
counts128 non-overlapping occurrences of11 consecutive recessive samples.
A dominant sample resets only the current consecutive run, preserving completed
occurrences. After the count, firmware clears both counters and reenables output.
The host requests recovery but does not generate the bit timings or count samples.
In the interrupted test, four occurrences are complete before a dominant sample;
output reenables10.915071 ms after the final release, after the remaining124
occurrences require at least10.912 ms. This is observed pin timing, not only a
late host-poll completion time.

The recovery loop has a4,096-sample budget,32.768 ms nominal plus fixed overhead.
Expiry returns local timeout with bus-off retained; a new recovery request begins
a new collection. Recovery is explicitly requested, not monitored continuously
by the idle request dispatcher. Recovery-timeout and suspension traffic handling
remain narrower than a general CAN node.

The passive equal-polarity loop is capped at64 samples. Alternating polarity
that never completes the flag returns local status25 with TXD released. Its
counter update is not treated as a completed normal flag. This finite abort is
a documented local policy, not complete handling of an arbitrary disturbed bus.

## Preserved failure and reusable code facilities

The original1,016-word prototype always treated a passive flag as six bit cells.
With dominant samples in cells1/2, the correct flag needs six recessive samples
in cells3–8. The independent peer catches the prototype publishing completion
before the resulting delimiter/intermission has finished. The corrected image
waits for equal polarity, with bounded monitoring, using four more instructions
overall after factoring a shared state-test leaf.

Generic leaf calls also solve a measured code-size failure: the preserved
[inlined prototype](../study/protocol_exploration/can_fault_inline_candidate.asm)
contains1,092 words and is rejected by the1,024-word model. The preliminary
call version uses1,016; corrected behavior uses1,020. The inlined listing is a
capacity comparison, not a passing timing implementation; removing calls would
also require timing rebalancing. This is not a lower bound on every possible
firmware implementation or a production storage decision.

Calls are not nested. Shared leaves emit FIFO bytes, update TEC and evaluate
passive state; CRC and wire processing still execute generic instructions.
The generic CALL facility and its historical unmapped cost were already studied
for USB. This follow-up changes no production RTL or physical-source hash.

## Verification and reproduction

```sh
uv run --locked pytest -q test/test_can_fault_units.py test/test_can_fault_equal_units.py
# Expected exit1: production capacity1,020>128.
uv run --locked python study/protocol_exploration/run_can_fault_equal.py can_fault_equal
uv run --locked python study/protocol_exploration/run_can_fault_equal.py can_fault_equal --expanded-model

# Expected exit1: preserved fixed-six-bit flag publishes too early.
uv run --locked python study/protocol_exploration/run_can_fault_equal.py can_fault_equal --expanded-model --fixed-flag --test-filter test_persistent_passive_ack_exception
```

The [peer](../study/protocol_exploration/can_fault_equal_peer.py) uses independent
frame encoding/CRC and checks public pins. Expected counter values come from
test arithmetic and runtime counter queries, not direct RAM writes or internal
DUT state. Five groups exercise:

- Sixteen missing ACKs taking TEC0→128 across requests; silent passive ACKs
  leaving128 unchanged; success restoring127; the next active flag crossing
  the threshold; and a passive flag overwritten by dominant bits.
- Thirty-two post-arbitration bit errors taking TEC0→256, passive signaling,
  output disable, input-drained bus-off rejection, interrupted recovery and
  later successful TX. Four completed groups survive a dominant interruption;
  output may reenable only after the remaining124 groups.
- REC increase/decrease, two arbitration winners and retained-payload retry,
  plus arbitration loss followed by missing ACK and eventual success, leaving
  TEC7 after the successful retry.
-256 bad-CRC receptions: REC128 forces passive behavior even with TEC0,
  REC saturates255 without bus-off, successful RX restores127, then the next
  TX error uses active signaling.
- A passive flag with64 alternating samples returns status25, followed by a
  successful receive with persistent counts intact.

Two source/capacity units cover both candidate generations and the1,092-word
inlining failure. The source-bound result snapshot records passing XML and
timing artifacts separately from the preserved negative comparison. CI runs
the corrected model and both units. These new counter tests use nominal clocks;
the819-word RX phase sweep remains separate frozen evidence.

## Remaining work

Correctly timed RX CRC/stuff/form error flags and the remaining counter rules
still need attempts. Full SJW/TX resynchronization, busy-bus service during
suspension/retry preparation, overload handling, reset-in-transfer and complete
request validation remain open. Recovery timeout and the arbitration stuff-bit
counter exception do not yet have dedicated integration cases.

There is no larger-core ASIC capacity/area/timing proof, new mapped regression,
or transceiver/board interoperability evidence. Historical fanout/signoff
limitations remain unchanged. With four model words free, further behavior
will require code reuse/compaction or a measured generic storage/control-flow
change; it must not be replaced by protocol-specific hardware.

Reference: [Bosch CAN2.0 specification](https://tech-tools.com/files/can2spec.pdf),
Part A sections3.1.3,3.1.5 and7, for equal-polarity passive flags, suspension,
counter exceptions, passive/bus-off thresholds and recovery qualification.
