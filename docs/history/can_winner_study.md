> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# CAN arbitration-winner reception and retained-payload retry

2026-10-25. The **811-word candidate** demonstrates arbitration-winner reception,
ACK and bounded retransmission using the existing generic1024×18/eight-register
model. It extends the frozen [701-word ACK-recovery experiment](can_ack_recovery_study.md)
without adding RTL, instructions, data memory or protocol hardware.
Production still rejects811>128. This remains an isolated firmware experiment.
Three independent-peer groups and all48 project unit tests pass. Exact commands,
source/XML hashes and timing observations are in the [result snapshot](can_winner_results.json).

The [builder](../study/protocol_exploration/build_can_winner.py) emits the
[candidate](../study/protocol_exploration/can_winner_candidate.asm).
The [independent peer](../study/protocol_exploration/can_winner_peer.py) supplies
the competing frame and requires the DUT itself to ACK it. No third node
provides that ACK. Earlier studies remain frozen comparisons.

## Firmware strategy and runtime contract

Operation4 starts TX of an arbitrary runtime11-bit identifier and DLC0–8
payload, receives valid lower-ID winners, then retries our original frame.
Arguments remain `[identifier_high3, identifier_low8, DLC]` at address0,
length3. Input count equals DLC; output limit33 accommodates three maximum-size
winner records. As in the earlier CAN experiments, these are valid-envelope
contracts; the firmware does not yet validate every request field.

Each received winner appends `[identifier_high3, identifier_low8, DLC, payload]`
to the output FIFO, with metadata0. Multiple records concatenate in reception
order. One terminal event reports input consumption, total returned bytes,
status and the number of our attempted transmissions. The same request can
encounter at most three arbitration/ACK attempts in total. Third-attempt
arbitration loss still receives/ACKs the winner, then completes with status22
and its data. Third missing ACK emits its flag/delimiter/intermission before
returning status24. A corrupted winner returns local CRC status16 without
ACK or partial output; it does not yet receive a correctly timed error flag.

Operations1=RX,2=legacy single-attempt TX and3=ACK-retry TX remain available.
All exchanges use50 MHz modeled execution,125 kbit/s standard data frames,
uio0=TXD and uio1=RXD through an external CAN transceiver/terminated bus.
The external component performs electrical signaling, not framing/arbitration.

Receiving the winner needs both the common arbitration prefix and our outgoing
payload. Firmware solves this without a second logical-bit buffer:

1. On first loading TX data, save its packed payload at private RAM136–143.
   These bytes normally hold completion detail/reserved fields, but no event
   is published while they contain payload. The host parameters retain our
   identifier/DLC. The input FIFO is consumed exactly once.
2. During TX, update a firmware CRC15 over logical bits, skipping inserted
   stuff bits. Cache the previous dominant-run length before fetching each bit.
3. On recessive-to-dominant arbitration loss, release TXD, correct that logical
   bit in the shared buffer and XOR the CRC polynomial to repair the mirrored
   prefix's last step. Restore receive stuffing/header state, then enter the
   existing receiver at the next sample. The received prefix and CRC are not
   recomputed too late from scratch.
4. Finish CRC/stuff/form checks, ACK the winner, append its decoded data, and
   rebuild our original logical frame/CRC from parameters and the packed copy.
   Retry after idle qualification, without host intervention or firmware reload.
5. Before publication, restore completion detail and clear all seven remaining
   saved bytes. The controller's terminal decoder checks reserved zeros.

The node is unavailable to receive a new frame while decoding output and
rebuilding TX. This controlled-bus experiment does not establish continuous
multi-node service, immediate retransmission or arbitrary competing traffic.

## Resource and timing budget

| Item | Candidate budget |
|---|---|
| Program |811 words,110 above ACK-recovery;213 free model words |
| Registers | All8: r0–r3 datapath, r4/r7 mirrored CRC, r5 attempt count, r6 software mode |
| Private RAM | Same128–254 footprint; packed copy reuses136–143 before event publication |
| FIFO |0–8 input bytes once; at most33 output bytes for three winners; one terminal record |
| TX bit/sample |400 clocks per bit; sample at300 clocks/75% |
| TX fetch | Existing50 clocks plus10-clock previous-run cache |
| TX CRC mirror |25 clocks including stuff selection, taken from the existing pre-sample wait |
| Loss handoff |19 clocks to handoff entry,37 state-repair clocks,343 padding clocks,1 branch:400 clocks to next RX sample |
| ACK recovery | Six-bit flag and delimiter/intermission scheduling retained; attempt limit now uses r5 |
| Winner-to-retry preparation |135.040–200.140 µs idle after intermission across12 recorded exchanges, including output decoding, frame/CRC rebuild and idle qualification |

CRC, run-length state, mode transitions and retry count are generic register,
RAM, shift/XOR, branch and wait instructions. There is no dedicated CRC,
arbitration, decoder, timer or retry engine. The program size is a measurement
of this implementation, not a lower bound on all possible firmware.

## Reproduction and verification scope

```sh
uv run --locked pytest -q test/test_can_winner_units.py
# Expected exit1: actual production program capacity.
uv run --locked python study/protocol_exploration/run_can_winner.py can_winner
uv run --locked python study/protocol_exploration/run_can_winner.py can_winner --expanded-model
```

The source/capacity unit checks generated-source freshness,811-word assembly on
the generic model and real production rejection. Independent pin-level groups
exercise all11 identifier-bit arbitration-loss positions, stuffed prefixes,
arbitrary unrelated winner/retained data and DLC0–8, two successive winners,
three-winner exhaustion with33 returned bytes, bad winner CRC/no ACK and later
successful requests. Compatibility cases retain legacy TX/RX, local loss,
missing-ACK flags/retry/exhaustion/dominant timeout, and a single operation4
that loses arbitration, loses ACK on retry and succeeds on its third attempt.

Expected wire bits/CRC come from the peer's independent encoder and polynomial
division, not the DUT instruction trace. The peer checks all frame cells,
requires only the DUT to ACK the winner, checks retained TX payload and final
completion after intermission, and watches400 µs for an unwanted fourth TX.
Its clock is nominal in these new arbitration cases; earlier frozen timing
sweeps are not silently attributed to this image.

CI runs the new candidate separately and uploads its XML, source-bound evidence
and `winner_timings.json`. This does not promote it into production firmware
or establish mapped/physical/hardware operation.

## Remaining work

Within-frame edge resynchronization is still absent. Broader error flags,
persistent transmit/receive error counters, error-passive/bus-off states,
overload handling, general busy-bus service, full request validation and
reset-in-transfer coverage remain open. Invalid winners currently terminate
the request locally. Extended identifiers, remote frames and CAN FD remain
outside this initial standard-data-frame scope.

Production program/register capacity, storage architecture, physical area/timing,
transceiver propagation and board interoperability remain unresolved. The
historical physical/signoff/fanout limitations are unchanged.
**Next task:** reproduce sensitivity to within-frame edge drift, then attempt
resynchronization with generic firmware or preserve a quantified blocker.

Reference: [Bosch CAN2.0 specification](https://tech-tools.com/files/can2spec.pdf),
Part A sections2,3.2,4 and8, for arbitration loss, receiver behavior, message
validation and bit synchronization. Passing selected cases is not a complete
CAN conformance claim.
