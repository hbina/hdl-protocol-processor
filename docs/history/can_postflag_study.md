> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# CAN counters after error flags

2026-10-25. A **1,023-word candidate** adds the receiver's first-post-flag+8
rule and repeated+8 accounting during prolonged dominance. Five model groups
and all53 project unit tests pass. One model instruction word remains.
Production still rejects1,023>128. No RTL, opcode or data RAM is added.

The [builder](../study/protocol_exploration/build_can_postflag.py) extends the
[RX-flag/counter firmware](can_receive_flags_study.md) on the same isolated
1024×18/eight-register generic CALL model. The
[candidate](../study/protocol_exploration/can_postflag_candidate.asm) preserves
runtime operations1–6, arbitrary standard-frame data and the transceiver-only
digital boundary. The host does not perform counter updates or line timing.

## Counter behavior and reproduced mismatch

After a completed receive-error flag, a dominant **first** following bit adds8
to REC, in addition to the normal receive-error increment. The old image returns
REC1 for the first test; the required value is9. The same independent wire test
passes on the new image. A dominant second bit after an initial recessive bit
does not trigger that first-bit rule.

The firmware also counts consecutive dominant bits after either RX or TX flags.
At post-flag dominant counts8,16,24 and32, it adds8 to the appropriate counter.
For an active flag, the initial six dominant flag bits make the first threshold
the14th consecutive dominant bit overall. For a passive flag, the threshold is
eight dominant bits following its completion. Recessive samples reset the
dominant-run counter; separate runs cannot accidentally accumulate together.

Both rules may apply. A receiver with eight consecutive post-flag dominant bits
adds1+8+8=17. The same transmitter case adds its normal8 plus the prolonged8,
without a receiver-only bonus. Passive missing-ACK exception handling remains
separate: silent passive ACK failure may add0 for the flag but still add8 for
the later prolonged dominant run.

REC remains capped255; TEC≥256 disables output as before. Error-flag selection
uses the pre-error state, including the threshold-crossing flag. The current
delimiter wait remains bounded to32 samples. A continuous32-bit dominant burst
is charged through its32nd sample, then returns local timeout25. Bursts ending
after24 dominant samples can still complete the eight recessive delimiter
samples within that budget. This is selected bounded recovery, not unlimited
disturbed-bus monitoring.

The stale local REC updater is removed: counted receive errors already update
REC in the shared physical flag handler. Unsupported header, DLC and retained
strict last-EOF/intermission diagnostics no longer charge a separate local
receive-error count. Those tail cases still return local status17 without data;
this does **not** implement legal EOF acceptance or overload/SOF behavior.

## Code and execution budget

| Item | Result |
|---|---|
| First integration |1,034 words; real1,024-word model rejection preserved |
| Initial compaction |1,028 words; still rejected |
| Final candidate |1,023 words;11 below the first integration |
| New data memory / hardware | None; r4 is reused as a modulo8 dominant-run counter |
| Counter increment implementation | Existing generic leaves; REC+8 repeats the saturating+1 leaf eight times |
| Delimiter sample interval |400 clocks/8 µs, measured on all receiver/transmitter timing rows |
| Longest loop work |104 clocks before fixed wait/branch padding |
| Error flag | Existing six-bit active/equal-polarity passive behavior; active pulse remains48 µs |
| Production |1,023>128; no new physical or board evidence |

The first-bit test uses the existing remaining-sample budget rather than new
persistent state. The periodic counter resets on recessive observations. Branch
padding keeps both added counter work and no-update paths at400 clocks per
sample. Clearing the run counter changes the final-delimiter branch by one
clock, so the following intermission wait is shortened accordingly.

Compaction preserves the full added behavior. Early unsupported-header/DLC
exits skip unnecessary work while retaining valid-frame timing. Passive suspend
waits share a non-nested generic leaf. Passive state returns directly in its
consumer register; its removed moves are compensated in the flag-start delays.
The initial polarity register assignment is unnecessary because the first
observation consumes one of six remaining equal samples either way. Two CRC
feedback paths use two right rotates of an isolated0/1 bit instead of a branch,
with the same wire-cycle costs. No special counter/CRC hardware is introduced.

## Verification and reproduction

```sh
uv run --locked pytest -q test/test_can_postflag_units.py
# Expected exit1: actual production capacity.
uv run --locked python study/protocol_exploration/run_can_postflag.py can_postflag
uv run --locked python study/protocol_exploration/run_can_postflag.py can_postflag --expanded-model

# Expected exit1: old image reports REC1 where the wire case requires9.
uv run --locked python study/protocol_exploration/run_can_postflag.py can_postflag --expanded-model --prior-counters --test-filter test_receiver_postflag_dominance
```

The [peer](../study/protocol_exploration/can_postflag_peer.py) calculates expected
increments from its independently chosen bus pattern and reads actual counts
through firmware operation6. It does not seed counters or derive expected data
from DUT RAM/instructions. A separate internal observer records delimiter sample
times only, checking exact8 µs spacing through every update path.

Five groups cover:

- Receiver first-vs-later dominance,0/1/7/8/16/24/32-bit runs, separated runs,
  CRC/stuff/form triggers, timeout charging and subsequent valid RX.
- REC126→127→136, active threshold-crossing signaling, passive mixed-polarity
  flags, saturation255 and successful RX restoring127.
- Transmitter accounting without the RX-only bonus, prolonged dominance,
  silent/overwritten passive ACK exceptions and successful TX decrement.
- Sixteen combined bit-error/prolonged-dominant exchanges taking TEC0→256,
  bus-off input draining/isolation, interrupted128×11 recovery and later TX.
- Unsupported profile exits without local REC charges, compact packet TX/RX,
  selected±5,000 ppm/400 ns valid-frame phase tests, winners and mixed retries.

Two additional generated listings preserve the1,034-/1,028-word model failures.
The unit checks them, final-source freshness and actual production rejection.
The [source-bound result record](can_postflag_results.json) includes exact
commands, positive/negative XML hashes, source hashes, capacity diagnostics,
all53 unit-test evidence and unchanged physical-source fingerprints.
CI runs the final image/unit and preserves XML and receiver/transmitter sample
records. The older-counter negative comparison has its own build directory.

## Remaining acceptance work

Bit-error accounting while actively sending an error/overload flag still needs
implementation and a transceiver-fault peer. Co-occurring/late-form accounting,
full SJW/TX timing, legal EOF/intermission/overload behavior, continuous busy-bus
service, full request/reset coverage and hardware interoperability remain open.
Longer fault monitoring and terminal-status precedence for a timeout after
bus-off are not established by the selected cases. Earlier recovery-timeout and
arbitration-stuff exception integration gaps remain.

The actual ASIC still has128×16 program storage/four registers. Model success
does not resolve production storage/encoding, mapped timing/area or historical
signoff/fanout limitations. One free model word makes further code costs a
measured design constraint rather than a reason to add protocol-specific RTL.

Reference: [Bosch CAN2.0 specification](https://tech-tools.com/files/can2spec.pdf),
Part A section7 rules1–3 and6, including simultaneous counter-rule applicability.
