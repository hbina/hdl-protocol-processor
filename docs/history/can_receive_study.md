> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# CAN receive: live CRC and ACK experiment

2026-10-25. This is an intermediate receive experiment, not completion of the
bidirectional CAN goal. The 335-word image cannot load on the production
128-word ASIC. An isolated 512-word model uses the same generic address
extension as the [Ethernet study](ethernet_capacity_study.md); production RTL,
assembler, memory size and physical results are unchanged.

Follow-up: the [TX experiment](can_transmit_study.md) now passes separately on
that model. Its 318-word image does not replace this baseline. A combined 622-word
source exceeds even 512 words. A copy now passes alternating TX/RX without reload
on the [larger generic frontier model](generic_frontier_study.md). This does not
change production capacity or this receive baseline's evidence.

## Demonstrated boundary and transaction

The candidate receives Classical CAN standard data frames with an 11-bit
identifier and 0..8 payload bytes at 125 kbit/s with a 50 MHz core clock.
An independent simulated transmitter supplies the identifier and payload on
every exchange. Firmware detects SOF, removes stuff bits, computes CRC15
while receiving, checks its residue, drives a dominant ACK, checks the fixed
tail and returns identifier/DLC/data through the existing runtime interface.
It repeats exchanges without reset or firmware reload.

Pin assignment is uio0=TXD, uio1=RXD; other pins remain inputs. Firmware drives
TXD high for recessive and low for dominant. An external **transceiver only**
must translate this to a terminated CAN differential bus and return its bus
state on RXD. The model resolves dominant as wired zero; it provides no
destuffing, CRC, packet recognition or acknowledgement on behalf of the ASIC.
No actual transceiver, propagation-delay budget or board integration is
validated by these tests.

The firmware is [can_candidate.asm](../study/protocol_exploration/can_candidate.asm).
[build_can_rx.py](../study/protocol_exploration/build_can_rx.py) generates its
conditional-path padding using ordinary WAIT/NOP instructions. It is a software
assembly builder; it introduces no new operation or protocol RTL. Every
received-bit decision and CRC step is present in the assembly listing.

## Valid request and result

Submit a normal runtime request with operation=1, zero input bytes, zero
arguments and output_limit=11. Parameters are unused. Firmware currently
assumes this valid envelope and does not validate operation or counts.

Successful output is `[identifier_high, identifier_low, DLC, payload...]`;
the high byte contains only the upper three identifier bits. Metadata is zero
for every output byte. The terminal event echoes request ID and epoch, sets
kind=1, reports status and output count, and consumes zero input bytes.

| Status | Meaning in this experiment |
|---|---|
| 0 | Frame accepted and ACK driven |
| 6 | Bus-idle/SOF wait expired |
| 16 | Nonzero CRC residue; no ACK |
| 17 | Invalid fixed-form field; no output |
| 18 | Unsupported RTR/IDE/reserved-bit pattern or DLC above 8 |
| 19 | Invalid stuff bit; no ACK |
| 20 | RXD did not observe the ACK driven by firmware |

The experiment accepts only standard data frames. An unsupported format is
reported to the host; this does not implement the required behavior of a
general CAN node encountering other traffic. Errors currently release TXD
and return status, without active error flags, error counters or bus-off state.
Returning an error and succeeding on the next controlled request is evidence
of local request recovery, not CAN fault-confinement conformance.

## Resource and timing measurements

| Resource | Current receive candidate |
|---|---|
| Instructions | 335 words; actual limit 128, also exceeds 256 |
| Event | RAM128..143, 16 bytes |
| Unstuffed bits | RAM144..241, up to98 bytes, one byte per logical bit |
| Receiver state | RAM242..249, 8 bytes |
| Total scratch span | 122 of 128 bytes; no SRAM needed for this experiment |
| CRC | r2/r3, 15 bits, polynomial 0x4599, initial 0, valid whole-frame residue 0 |
| Physical receive period | 400 core clocks =8 µs; includes a stuff bit when present |
| Longest balanced normal bit path before padding | 143 clocks |
| Live ACK | 400 clocks dominant; asserted in ACK slot, released for delimiter |
| Idle qualification | Eleven sampled recessive bit times before SOF wait |
| No-SOF polling | Bounded nested 8-bit counters, about5.25 ms after arming |

The initial sample is near75% of the SOF bit after synchronized edge detection.
Conditional paths are padded to a constant 400-clock physical-bit loop. CRC
processing covers SOF through the received CRC sequence; stuff bits are checked
and excluded. The last CRC bit may itself require a following stuff bit, which
is consumed before the CRC delimiter and ACK scheduling.

This demonstrates substantial execution margin at 125 kbit/s, but instruction
capacity is already a concrete blocker **before adding transmit**. It does not
prove that a 335-word physical implementation fits the tile allocation. Code
density, generic subroutines/control flow, or larger program storage remain
candidate solutions. No production architecture change has been selected.

## Verification and reproduction

Recorded results and source hashes are in
[can_receive_results.json](can_receive_results.json). Run from the repository root:

```sh
# Regenerate the reviewable generic-instruction listing.
uv run --locked python study/protocol_exploration/build_can_rx.py

# Actual ASIC capacity: exits1, program 335 words exceeds 128.
uv run --locked python study/protocol_exploration/run_can.py can

# Explicitly counterfactual model; not production ASIC coverage.
uv run --locked python study/protocol_exploration/run_can.py can --expanded-model
```

The peer uses polynomial long division, independently of the firmware's
two-byte LFSR. Expected data comes from its own frame construction. A separate
internal execution observer checks actual sample-instruction spacing; it does
not supply expected wire contents or steer the peer.

Four tests cover:

- Repeated receives, all lengths 0..8, IDs including 0 and 0x7ff, zero/one/random
  data, and a final-CRC-bit stuffing boundary.
- Bad CRC, invalid stuffing, dominant CRC delimiter, unsupported RTR/IDE/DLC,
  no ACK on these rejected frames, and a later successful request.
- Five start phases across the 20 ns core clock at relative peer rates
  -1000,0,+1000 ppm, with an 8-byte frame. These are tested operating points,
  not a general oscillator-tolerance certification.
- Missing SOF timeout followed by a successful receive without reset/reload.

Successful exchanges additionally check identifier/data, completion counts,
empty runtime state, exact 8 µs sampling intervals, and a single 8 µs dominant
ACK pulse near the peer's ACK cell. ACK phase drift must remain within 1.6 µs
in the tested frequency matrix. Fault cases return no output.

## Remaining work

1. Bring combined TX/RX to production. The frontier model now alternates
   modes without reload; production storage and physical implementation stay open.
2. Extend arbitration-loss handling with winner reception, bounded retry policy, falling-edge
   resynchronization and explicit bit-time/propagation parameters. Current RX
   hard-synchronizes only at SOF; it does not resynchronize within a frame.
3. Implement error flags and fault confinement, then test error-frame recovery,
   full CAN error recovery and actual transceiver delays. Separate TX tests now
   cover missing ACK and initial arbitration-loss release, without winner RX.
4. Extend validation, initial bus-idle detection and EOF/intermission handling.
   The current fixed-tail check is intentionally stricter than full CAN rules
   for legal last-EOF-bit variations and overload traffic. Stuck-bus and reset
   during transfer are not yet covered.
5. Resolve program capacity, rerun the production regression and measure
   synthesis/place-and-route impact before claiming ASIC support.

[USB packet reception](usb_receive_study.md) now has model evidence, while its
response deadline and enumeration remain unresolved. Neither the nine-protocol
exploration nor CAN's bidirectional acceptance gate is complete.

## Protocol references

- [CiA CRC in CAN frames](https://can-cia.org/can-knowledge/cyclic-redundancy-check-crc-in-can-frames)
  gives the Classical CAN polynomial and CRC-dependent acknowledgement rule.
- [Microchip CAN error detection](https://onlinedocs.microchip.com/oxy/GUID-B822915F-C375-4172-91BD-AB6F326EB783-en-US-1/GUID-358DD068-E7B7-41C9-8596-8C358E87DED9.html)
  describes the error classes and error-frame requirements that remain partly
  unimplemented here.
- [Analog Devices CAN implementation guide](https://www.analog.com/en/resources/app-notes/an-1123.html)
  distinguishes the transceiver and controller boundary. Full normative CAN
  timing/conformance review remains necessary as the experiment develops.
