> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# CAN receive-error flags and firmware compaction

2026-10-25. A **1,021-word candidate** adds timed receive CRC, stuffing and
selected form-error flags to the previous counter/winner/retry firmware. It
uses the same generic CALL model and data memory. No RTL, opcode or hardware
engine is added; three model words remain. Production still rejects1,021>128.
Five model groups and all52 project unit tests pass. Exact commands, source/XML
hashes, capacity failures and timing records are in the [result snapshot](can_receive_flags_results.json).

The [initial builder](../study/protocol_exploration/build_can_rx_flags.py)
produces1,069 words and fails the1,024-word model limit. The
[compaction builder](../study/protocol_exploration/build_can_rx_flags_compact.py)
emits the [1,021-word image](../study/protocol_exploration/can_rx_flags_compact_candidate.asm)
with the same wire-cycle budgets. The oversized image and the older
[local-error-only image](can_fault_state_study.md) remain reproducible comparisons.

## Error timing and shared state

The request/pin/rate contracts are unchanged from the fault-state study:
50 MHz modeled execution,125 kbit/s standard frames, uio0=TXD/uio1=RXD and an
external transceiver/terminated bus with no external CAN controller. Operations
1–6 still provide RX, single/retried/winner-aware TX, bus-off recovery and
counter queries. Arguments/data remain arbitrary runtime inputs within DLC0–8.

Receive errors now enter the shared firmware flag/delimiter/intermission
sequencer. The pre-error TEC/REC state selects active or passive signaling;
a completed RX error flag increments REC once, leaving TEC unchanged. The
received invalid frame produces no payload output. Prior valid winner records,
if present, retain their previous bounded output contract.

| Error | Selected flag start and status |
|---|---|
| Stuffing violation | Next bit after the invalid stuff sample; status19 |
| CRC mismatch | First EOF bit, after ACK delimiter; status16; do not ACK |
| Dominant CRC delimiter | Following ACK slot; status17; no normal ACK |
| Dominant ACK delimiter / first six EOF bits | Following bit; status17 |

CRC status is kept pending while the possible final CRC stuff bit is consumed.
A stuffing violation there takes the immediate signaling path, rather than
being hidden by the earlier CRC result. The peer supplies a vector exercising
both a bad CRC with valid final stuffing and a bad final stuff bit on that frame.
CRC and ACK-delimiter faults may coincide; the pending CRC result remains the
reported terminal status when they share the same flag boundary.

Unsupported-header status18 remains a local result. The older strict/local-only
handling of dominant last-EOF/intermission samples also remains: it does not
implement legal last-EOF variations, overload frames or third-intermission SOF
joining. Those cases are not silently converted into incorrectly timed active
error flags. The ACK-loopback error path is routed to the shared handler but
does not yet have its own transceiver-fault integration case.

Active flags drive six dominant cells. Passive flags wait for six sampled bits
of equal polarity, including an injected dominant overlap, with the existing
64-sample cap. Delimiter wait remains bounded to32 samples. Error completion
follows eight recessive delimiter samples and three intermission cells.
Persistent counters and bus-off monitoring retain the earlier documented limits.

## Code and execution budget

| Item | Current evidence/budget |
|---|---|
| Program |1,069 words before compaction;1,021 after, saving48;3 free model words |
| Hardware model | Existing1024×18/eight-register generic leaf-call core |
| RAM | Existing private128–255 layout, with persistent REC250/TEC251+255; no added storage |
| Normal RX work |147 clocks before phase polling, including pending-CRC handling |
| RX phase window |26 polls,4 clocks apart, offsets152–252; bounded correction remains partial CAN timing |
| Immediate RX fault |151 clocks to shared preparation; flag at200 clocks after50% sample |
| CRC fault | Wait through CRC delimiter/ACK/ACK delimiter, then flag at EOF boundary |
| TX timing | Existing400-clock bit and75% sampling budgets preserved |
| Active flag measurement |8 recorded cases, each2,400 clocks/48 µs; start22–117 ns after peer's corresponding boundary |
| Valid RX clock/phase sweep | Selected−5,000/0/+5,000 ppm and400 ns steps on8-byte frames; sample phase45.955–59.219% |

The peer permits at most300 ns flag-start delay for synchronized-input phase
and observes GPIO every10 ns. The flag duration is checked from public pin
transitions, not inferred only from assembly delays. These are nominal-clock
error-flag tests and selected valid-frame drift tests, not a transceiver
propagation-delay or general oscillator-tolerance certification.

Compaction changes only firmware:

- Six TX bit-unpack loops share one generic leaf. RX ID/payload packing shares
  another, with a separate byte counter instead of repeated pointer-modulo work.
- Conditional XOR replaces repeated shifts when forming software CRC feedback.
  Added wait padding preserves on-wire path costs; offline TX preparation may
  finish sooner. The polynomial and all CRC decisions remain instructions.
- Dead initializations and unreachable padding are removed. The leaves are
  not nested and add no dedicated protocol operation.

## Verification and reproduction

```sh
uv run --locked pytest -q test/test_can_rx_flags_units.py
# Expected exit1: production capacity1,021>128.
uv run --locked python study/protocol_exploration/run_can_rx_flags.py can_rx_flags
uv run --locked python study/protocol_exploration/run_can_rx_flags.py can_rx_flags --expanded-model

# Expected exit1: older1,020-word image emits no CRC error flag.
uv run --locked python study/protocol_exploration/run_can_rx_flags.py can_rx_flags --expanded-model --local-errors --test-filter test_receiver_error_flags
```

The unit checks deterministic generation, the1,069-word model rejection and
the real production rejection. The [peer](../study/protocol_exploration/can_rx_flags_peer.py)
uses its own polynomial-division CRC/frame encoder and public resolved pins.
An internal observer measures sample placement only; it does not generate
expected data or drive the peer from DUT execution state.

Five model groups cover receive-error timing and no invalid output; DLC0–8
TX/RX through the shared packers plus valid-frame drift/steps;256 bad-CRC
receptions through passive threshold/saturation and a valid RX restoring127;
TX passive counters/winners/mixed retries; and bus-off rejection/interrupted
recovery followed by valid RX. Transactions repeat without reload/reset inside
each group. Queries check firmware counter values through the normal runtime ABI.

CI runs the compact image and unit separately, uploading XML, source-bound
evidence and error/phase timing records. The negative local-error comparison
uses its own build directory and provenance; it is an explicit manual command.
The default production regression and physical-source hashes are unchanged.

## Remaining acceptance work

This is not complete CAN fault confinement. The receiver's additional+8 rule
for a dominant first bit after its flag, flag bit errors and prolonged-dominant
counter rules still need work. Updates for co-occurring errors and ACK-success
followed by later form faults remain narrower than full normative counter rules.
Aborted flag waits retain the existing local status25 policy rather than full
disturbed-bus recovery.

Full SJW/TX resynchronization, legal EOF/overload/intermission variations,
continuous reception during suspension/retry preparation, full request/reset
coverage, real transceiver timing and hardware interoperability remain open.
The previous recovery-timeout and arbitration-stuff counter-exception test gaps
are preserved. Production program/register/storage and physical fit are unresolved;
the historical signoff/fanout limits remain unchanged.

Reference: [Bosch CAN2.0 specification](https://tech-tools.com/files/can2spec.pdf),
Part A sections6.2 and7, for CRC-vs-other-error flag scheduling and counter rules.
