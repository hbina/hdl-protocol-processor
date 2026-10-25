# CAN transmit and combined-image capacity

Follow-up on 2026-10-25: the [generic frontier study](generic_frontier_study.md)
now runs a copy of the 622-word combined program on a 1024×18/eight-register
model, including alternating TX/RX without reload. The 512-word results and
capacity-only source below remain frozen baseline evidence. Production
capacity/physical implementation and remaining CAN node behavior stay open.

2026-10-25. Firmware now has an independent transmit probe alongside the
[receive baseline](can_receive_study.md). Both use generic instructions for
all protocol work. Production RTL and its 128-word instruction memory are
unchanged; neither probe fits that capacity.

**Evidence boundary:** four TX tests pass on an explicit 512-word model.
The 318-word TX image and 335-word RX image are tested separately. A combined
622-word source shares request handling and event publication, but fails
assembly even for the 512-word model. The combined source was **not** simulated on that 512-word model; those results
are not a passing bidirectional demonstration. The frontier follow-up above
tests a copy on a larger model.

## TX transaction and external boundary

The [transmit firmware](../study/protocol_exploration/can_tx_candidate.asm)
accepts an 11-bit identifier and 0..8 arbitrary payload bytes at runtime. It
builds a Classical CAN standard data frame, calculates CRC15, inserts stuff
bits, sends at 125 kbit/s, monitors RXD, checks ACK and fixed tail fields, and
returns a terminal event. Repeated successful and failed requests run without
reset/reloading this TX image.

Use operation=1, arguments_address=0, arguments_length=3 and arguments
`[identifier_high_3_bits, identifier_low_8_bits, DLC]`. Supply exactly DLC input
bytes and output_limit=0. These are valid-envelope experiments; firmware
does not yet validate every operation, argument or length field. The event
echoes request ID/epoch, sets kind=1, reports input_consumed=DLC and produces
no output. Payload is fully buffered before the bus exchange, so a failed TX
does not leave input bytes stranded in the runtime FIFO.

Pins match the receive probe: uio0=TXD, uio1=RXD, others inputs. TXD=1 means
recessive and TXD=0 dominant. An external electrical transceiver and correctly
terminated differential bus are required. No external CAN controller,
CRC/stuffing engine or packet processor is allowed. The simulated peer
resolves dominant as wired zero and has its own frame encoder/CRC oracle.
No real transceiver or board has been validated.

| Status | TX probe meaning |
|---|---|
| 0 | Frame sent, ACK observed, fixed tail passed |
| 6 | Initial bus-idle qualification expired |
| 17 | Dominant CRC delimiter, ACK delimiter or fixed tail bit |
| 21 | Monitored bit differs outside a valid identifier arbitration-loss case |
| 22 | Recessive identifier bit lost arbitration; TXD released |
| 24 | No dominant ACK observed |

Arbitration handling currently releases the bus and reports status. It does
not receive/ACK the winner or retry automatically. The arbitration test uses
a valid lower-ID winner and a third simulated receiver to ACK that winner.
An inserted stuff-bit mismatch is classified as a bit error, not arbitration
loss. Missing ACK and bit/form errors return status without the required CAN
error flag or fault-confinement state. These are local failure/recovery probes,
not a conforming CAN node.

## Generic instruction and storage budgets

[build_can_tx.py](../study/protocol_exploration/build_can_tx.py) emits ordinary
loads/stores, pin operations, shifts, masks, XORs, branches and WAIT/NOP padding.
The software builder reuses the receive study's generic path-balancing helper.
CRC and stuffing execute at runtime as instructions; the builder receives no
transaction data and does not precompute a host-supplied waveform.

Firmware first expands the unstuffed SOF/header/data into one-byte bits in
private RAM, computes CRC over them with polynomial 0x4599 and initial 0, then
appends 15 CRC bits. The timed loop chooses either the next logical bit or a
required complementary stuff bit. It also consumes a final pending stuff bit
before entering the unstuffed CRC delimiter.

| Resource | TX probe |
|---|---|
| Program | 318 words; production limit 128 |
| Terminal event | RAM128..143 |
| Logical frame buffer | RAM144..241, up to 98 bits stored as bytes |
| State/temp span | RAM242..254, with unused locations |
| Total scratch address span | 127 of 128 bytes; fits existing data RAM |
| Balanced next-bit fetch | 50 core clocks |
| TX physical bit period | 400 core clocks =8 µs |
| RXD sample point | 300 clocks after TXD update, nominal 75% |
| No-fault precomputed CRC | Offline before SOF; live RX CRC remains in RX image |

The TX bit period is independent of CRC branches, run length and logical
versus stuffed bits. The independent peer checks the complete bitstream at
its own sample point and checks actual pin transitions against an 8 µs grid.
CRC delimiter, ACK, ACK delimiter, EOF and intermission are handled separately
from the stuffed section.

## Combined source and reproduced blocker

[build_can_duplex.py](../study/protocol_exploration/build_can_duplex.py)
combines the two instruction listings, shares the loader-facing request loop
and completion code, namespaces internal labels, and dispatches operation 1 to
RX and operation 2 to TX. TX arguments remain ID high/ID low/DLC; RX takes no
arguments and allows 11 output bytes. This is a **capacity-only** source, not
tested execution. Invalid operation values are not yet rejected.

The generated [combined candidate](../study/protocol_exploration/can_duplex_candidate.asm)
contains 622 words. Two preserved assembly checks fail before execution:

```sh
uv run --locked python study/protocol_exploration/build_can_duplex.py --check-capacity 128
# Combined CAN capacity: program contains 622 words; maximum is 128

uv run --locked python study/protocol_exploration/build_can_duplex.py --check-capacity 512
# Combined CAN capacity: program contains 622 words; maximum is 512
```

This is a measured size of the current candidate, not a lower bound on all
possible implementations. Further sharing, compact data representation and
code-density improvements remain possible. A larger program store would also
need generic control flow that can address it: the current experimental branch
extension addresses only 512 words. Options include a revised generic branch
encoding, generic subroutines/indirect control flow, or program banking. No
production encoding or SRAM decision has been made, and there are no physical
fit/timing results for either expanded model.

## Tests and commands

The [TX evidence record](can_transmit_results.json) saves commands, test names,
source hashes and capacity diagnostics. From the repository root, with the
locked Python dependencies and Icarus available:

```sh
uv run --locked python study/protocol_exploration/build_can_tx.py
uv run --locked python study/protocol_exploration/build_can_duplex.py

# Expected exit 1: standalone TX also exceeds production capacity.
uv run --locked python study/protocol_exploration/run_can_tx.py can_tx

# Explicit expanded model; separate build directory from the RX baseline.
uv run --locked python study/protocol_exploration/run_can_tx.py can_tx --expanded-model
```

Four TX tests cover:

- Every DLC 0..8, arbitrary seeded ID/data, IDs 0/0x7ff, zeros/ones, repeated
  transactions and stuffing after the last CRC bit.
- Missing ACK, post-arbitration recessive-bit overwrite, lower-ID arbitration
  loss, inserted stuff-bit overwrite, malformed fixed tail fields and later
  successful requests without reset/reload.
- Independent peer rates -1000/0/+1000 ppm with ACK assertion delays 0/400/800 ns
  on 8-byte frames. These are simulated operating points, not general CAN
  timing certification or a transceiver propagation-delay specification.
- Stuck-dominant idle timeout after buffering the full input, then a successful
  exchange on a released bus.

The peer calculates CRC by polynomial division rather than using firmware's
two-byte LFSR. It checks every expected transmitted bit, output-enable scope,
transition timing, terminal counts/status and an empty runtime channel.
Successful completion must be observed after the frame and intermission.
The four RX baseline tests and their source-bound evidence remain unchanged.
CI runs the TX experiment separately from RX and production RTL regression.

## Remaining acceptance work

- Bring combined TX/RX to production. A copy now executes on the generic
  frontier model; the 128-/512-word capacity failures below remain valid.
- Receive the winning frame after arbitration loss and implement bounded
  retries, error flags, error counters and fault confinement.
- Add within-frame edge resynchronization, explicit bit-time/propagation
  parameters and broader peer timing/error-frame tests.
- Complete request validation, initial idle detection, legal EOF/intermission
  variations, reset-in-transfer, mapped verification and real transceiver tests.

The nine-protocol goal remains open. [USB packet reception](usb_receive_study.md)
now has model evidence and reproduced response-timing/capacity failures;
enumeration remains absent. The remaining CAN node behavior stays tracked.

References: [CiA CRC and ACK](https://can-cia.org/can-knowledge/cyclic-redundancy-check-crc-in-can-frames),
[Microchip CAN error classes](https://onlinedocs.microchip.com/oxy/GUID-B822915F-C375-4172-91BD-AB6F326EB783-en-US-1/GUID-358DD068-E7B7-41C9-8596-8C358E87DED9.html),
and the [receive study's protocol references](can_receive_study.md#protocol-references).
Full normative timing/conformance review remains necessary.
