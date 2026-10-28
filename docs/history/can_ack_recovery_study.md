> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# CAN missing-ACK recovery in generic firmware

2026-10-25. A **701-word candidate** extends the frozen622-word combined CAN
experiment with an active error flag and at most three transmit attempts after
missing ACK. Three independent-peer groups and one source/capacity unit pass
on the existing1024×18/eight-register model. Production still rejects the image:
701 words exceeds128. No RTL, opcode or protocol-specific hardware is added.

The [builder](../study/protocol_exploration/build_can_recovery.py) emits the
[candidate](../study/protocol_exploration/can_recovery_candidate.asm).
The [result snapshot](can_ack_recovery_results.json) records source/XML hashes,
commands, timing observations, capacity rejection and unchanged physical sources.
Earlier RX, TX and combined candidates remain frozen comparison evidence.

## Selected request and wire behavior

The digital boundary remains uio0=TXD, uio1=RXD, output enable1, through an
external CAN transceiver with a wired-dominant bus. All framing, CRC15,
stuffing, ACK interpretation, retry decisions and delays execute as ordinary
generic instructions at the modeled50 MHz clock and125 kbit/s bit rate.
There is no host intervention between attempts.

Operations1=RX and2=single-attempt TX retain the previous valid-envelope
contracts. Operation3 selects ACK-error recovery. Its three argument bytes are
`[identifier_high3, identifier_low8, DLC]`, with an11-bit identifier and DLC0–8.
The host supplies DLC arbitrary payload bytes through the input FIFO, once.
The first TX builds the logical frame and CRC in private RAM; retries reset
only the frame pointer and stuffing state. They reuse the buffered frame
rather than rereading popped input or requesting a host-generated waveform.

For operation3, event detail is the number of attempted transmissions1–3.
Success returns status0; three missing ACKs return status24. Each missing ACK,
including the last, triggers a six-dominant-bit active error flag at the next
bit boundary. Firmware then releases TXD, waits for eight consecutive recessive
delimiter samples and checks three recessive intermission cells. If attempts
remain, the next SOF begins at the following bit boundary. A bus held dominant
through the bounded delimiter wait, or a dominant intermission sample, returns
local status25 with TXD released. It does not implement CAN overload handling.

Other errors retain the earlier local statuses and behavior. In particular,
arbitration loss still releases TXD and reports status22; it does not yet
receive the winner or retry after that winner. Operation2 still returns a
local missing-ACK result without emitting an error frame. These legacy modes
are preserved for comparisons, not claimed as complete CAN-node operation.

## Measured resource and timing budget

| Item | Current result |
|---|---|
| Program |701 instructions,79 above the frozen combined image;323 free model words |
| Registers | Existing r0–r3 datapath plus r4=remaining attempts, r5=attempt count, r6=recovery mode; no new register semantics |
| Private RAM | Existing128–254 layout retained:16-byte event,98 logical-bit bytes,13 state bytes; no extra buffer |
| CAN bit |400 core clocks,8 µs |
| ACK sample to flag start |100 core clocks,2 µs from the75% sample to the next cell boundary |
| DUT active flag |2,400 core clocks,48 µs; public-pin edge measurements recorded |
| Delimiter sampling |400 clocks apart; require8 consecutive recessive samples; at most32 samples |
| Retry start | After the delimiter and3 full intermission cells, without host service |
| Production capacity | Reproduced failure701>128; larger-model execution is not ASIC fit evidence |

The public bus resolver observes GPIO every10 ns. The independent peer requires
each flag edge within10.001 ns of its expected bit boundary, allowing its1 ps
SOF wakeup offset. It checks the next retry SOF within1 ns, all frame bits at
75% of each cell, and completion after the final frame/intermission. This
observer tolerance is smaller than one20 ns core clock and far smaller than
one8 µs CAN bit. No instruction/PC trace supplies expected wire values.

The delimiter timeout counts samples, not complete elapsed request time.
There is no clock-rate/jitter sweep for the new recovery path. Earlier TX/RX
timing sweeps remain evidence for their frozen images only.

## Verification and reproduction

```sh
uv run --locked pytest -q test/test_can_recovery_units.py
# Expected exit1: production128-word rejection.
uv run --locked python study/protocol_exploration/run_can_recovery.py can_recovery
uv run --locked python study/protocol_exploration/run_can_recovery.py can_recovery --expanded-model
```

The [peer](../study/protocol_exploration/can_recovery_peer.py) uses independent
polynomial-division CRC and frame/stuff encoding. Its three groups cover:

- Every DLC0–8, arbitrary seeded identifiers/payloads, two/three attempts and
  eventual ACK, repeated requests without reset/reload, zero/one data patterns,
  and the same independently checked frame on every attempt.
- Three missing ACKs with exactly three flags and no fourth attempt; successful
  RX afterwards; a bus held dominant during recovery producing status25;
  subsequent valid RX and first-attempt TX success.
- Legacy TX/RX, bad RX CRC, single-attempt missing ACK and lower-ID arbitration
  loss, followed by a successful operation3 retry exchange.

Nominal overlapping-error tests inject another six-bit dominant flag starting
one cell later, extending the bus's dominant sequence by one bit. Separate
cases use no peer flag and a three-bit extension. The latter is a dominant
extension stress injection, not a complete second node's error-state model.
The peer checks DUT release after exactly six cells even while the bus remains
dominant, then checks recovery against the resolved bus.

CI runs this model and its unit separately and uploads XML, source-bound
evidence and `retry_timings.json`. The default production regression retains
the earlier small images. The source/capacity unit checks deterministic
generation and real production rejection; the wire tests provide behavioral
evidence. Physical-source hashes remain those of the historical v0.2 build.

## Remaining acceptance work

This is an **ACK-error recovery experiment assuming an error-active node**,
not complete CAN error management. It does not implement persistent error
counters, error-passive transition, bus-off or recovery from bus-off. Counts
restart per request. Other error types still lack correctly scheduled flags.
It also lacks winner reception/retry after arbitration loss, within-frame
edge resynchronization, general peer-error/overload handling, full envelope
validation and reset-in-transfer coverage. A bounded status25 abort is not
proof of standard-compliant recovery on a busy multi-node bus.

Production storage, physical timing/area, transceiver propagation and hardware
interoperability remain unresolved. The earlier fanout/signoff limitations
remain unchanged. The next functional task is to attempt **arbitration-winner
reception and subsequent retransmission**, including preserving the outgoing
payload while RX uses private storage. Keep decisions in firmware, preserve
any reproduced blocker and measure resources before changing generic hardware.

Protocol reference: [Bosch CAN2.0 specification](https://tech-tools.com/files/can2spec.pdf),
Part A sections3.1.3,3.1.5,6.2 and7, for error-frame timing, intermission and
fault confinement. Those requirements motivate this narrow experiment; its
passing cases do not establish full conformance.
