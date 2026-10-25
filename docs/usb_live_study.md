# Live USB packet decoding and CRC on a generic CPU

2026-10-25. This experiment meets the **packet-response timing window** on an
isolated model. It is not an enumerating USB device, a complete USB transaction
or production ASIC support. Packet decoding, stuffing, CRC and ACK generation
remain entirely generic instructions.

The [buffered baselines](usb_receive_study.md) still reproduce their timing
failures. The new 947-word program processes each bit while it arrives, using
eight registers and a generic one-level CALL/RETURN facility. Five model tests
pass, including payload/CRC checks and a 1.33–4.33 µs response-window assertion.
The phase/frequency sweep measures ACK latency between 2.435 and 2.634 µs at the
digital transceiver boundary. Production RTL and its 128-word store are unchanged.

## What changed and why

Buffered decoding took about 92 µs after an eight-byte packet, followed by
another 33 µs for CRC. Optimizing only post-packet CRC would not solve the
deadline. The new firmware instead unrolls eight logical bit positions across
three fractional clock phases. Each real or stuffed physical cell advances the
phase; only a real data bit advances the logical bit position.

The [assembly](../study/protocol_exploration/usb_live_candidate.asm) performs:

- VP/VM sampling, SE0 detection and NRZI transition decoding.
- Run-length tracking, rejection/removal of stuffed zeros, and byte assembly.
- A software CRC step after every non-stuffed bit.
- Byte-boundary stores and an overrun guard at the next byte's first real bit.
- EOP, length and PID validation, CRC syndrome comparison, then optional ACK.

Normal paths consume a fixed 33/33/34-clock schedule at 50 MHz. Ones and zeros
are balanced with ordinary NOP/WAIT instructions. The CALL, CRC body and RET
consume 14 clocks; the longest normal data path before final padding/jump is
31 clocks at a byte boundary. The instruction trace checks actual sample
spacing, including paths that consume a stuff bit without advancing the byte.
Trace data does not steer the peer or supply expected packet contents.

There is no within-packet edge resynchronization yet. The tested phase/rate
matrix is an operating envelope, not the full USB jitter-tolerance requirement.

## Generic subroutines and capacity evidence

[generic_call_frontier.py](../study/protocol_exploration/generic_call_frontier.py)
wraps the frozen [frontier model](generic_frontier_study.md). It adds a ten-bit
return-address register and two protocol-independent instructions:

| Instruction | Encoding | Semantics |
|---|---|---|
| `CALL target` | opcode 0, bit 10 set, target in bits 9..0 | Save PC+1; jump to target |
| `RET` | `0x0800` | Jump to the saved address |

The link resets on reset and configuration exit. This is a **single-level,
leaf-subroutine facility**: nested calls overwrite the link and are unsupported.
Valid assembler-generated legacy NOPs remain zero and keep their behavior.
Production RTL and assembler are not changed.

The generic CRC subroutine contains shifts, masks, XORs and branches; CALL/RET
hardware knows nothing about USB or CRC. Without sharing that routine, the
same unrolled program has 1,221 words and fails the 1,024-word model capacity.
With calls it has 947 words. The generated
[inline candidate](../study/protocol_exploration/usb_live_inline_candidate.asm)
preserves that code-density failure. Subroutines could also share repeated
bit/CRC/timing routines in CAN or I2C; those are further code-density experiments,
not implemented protocol accelerators.

The 947-word result leaves only 77 words in this model. Token/endpoint/control
state may require more density or storage; no claim is made that the complete
USB stack fits. Larger physical storage and host-capability/version choices
remain unresolved.

## CRC computation and static constants

All bits, including PID, enter a live reflected 0xa001 CRC with initial 0xffff.
Including PID avoids a per-bit mode decision on this tight schedule. At EOP,
firmware checks a fixed syndrome for the validated PID and payload length,
equivalent to checking the ordinary data-only USB CRC.

The [builder](../study/protocol_exploration/build_usb_live.py) emits a
[36-byte constant table](../study/protocol_exploration/usb_live_constants.json)
for two PIDs and nine lengths. It is independent of payload contents. The host
loads it as firmware data into parameter RAM; it does not generate or validate
the transaction's CRC. The ASIC calculates the live checksum from received pins.
The independent peer still generates expected FCS with polynomial division.

Four new unit tests check CALL encoding/legacy compatibility, constant
syndromes for 1,800 varied payload cases and rejection of every single data/CRC
bit error in an eight-byte frame for both PIDs, plus generated-source freshness and
inline/production capacity failures. Wire tests separately reject
bad CRC, including wrong received check bytes.

## Request ABI and limits

The transceiver boundary and pins match the buffered study: TUSB1106, uio0/1
VP/VM, uio2/3 VPO/VMO, uio4 active-low OE and uio5 SOFTCON, with SPEED/SUSPND
strapped low. There is no external USB controller or packet-processing offload.

Valid runtime requests use operation=1, arguments_address=0,
arguments_length=37, input_count=0 and output_limit=11. Arguments contain
`[diagnostic_ACK_enable, constant_table_bytes...]`; the table is identical for
all payloads and both PIDs. Firmware assumes this envelope. A deployed loader
could initialize the constants once; this probe uses the existing submit API.

Each request receives one isolated DATA0/DATA1 packet with 0..8 bytes. Successful
output is PID/payload/two CRC bytes with zero metadata. Completion reports no
input consumed and 3..11 output bytes, with ID/epoch echoed. Error statuses
remain 6 timeout, 16 CRC, 17 form/SYNC/SE1/alignment, 18 unsupported PID, 19 stuffing,
20 overrun and 21 invalid PID complement. Invalid packets produce no output or
ACK, and later requests can succeed without reset/reload.

Memory use is event 128..143, packet bytes 144..154 and host parameter constants
1..36. Live state is in the eight generic registers. The baseline's large raw
line-state buffer and post-capture decode/CRC passes are removed.

The ACK is still diagnostic: the probe does not first validate an addressed
OUT/SETUP token. Passing its timing check does not make it a valid endpoint
transaction. Token CRC5, address/endpoint matching, reset, endpoint-zero
enumeration, setup/data/status phases, duplicates/toggles and arbitrary IN data
transmission remain unimplemented.

## Tests, results and reproduction

[usb_live_results.json](usb_live_results.json) binds the results to source hashes.
Five model cases cover:

1. Both DATA PIDs at all lengths 0..8 with arbitrary seeded data, zeros/ones,
   passive reception and stuffing after the final CRC bit. Every diagnostic ACK
   is waveform-checked and must meet the minimum and maximum response delay.
2. CRC/PID/stuff/SYNC/SE1/EOP/oversize/empty/unsupported-PID failures, missing
   final stuff bit and recovery, with no ACK on rejected packets.
3. Five SOP phases across the 20 ns core period at peer rates -1000/0/+1000 ppm,
   checking bytes, CRC, capture periods and ACK deadline for an eight-byte frame.
4. Missing-SOP timeout followed by a valid packet without reset/reload.
5. Generic CALL/RETURN across program banks and return-link reset on reload.

The ten legacy UART/SPI/I2C-example/JTAG/runtime tests also pass on the call
model. Together with the existing unit suites there are 32 passing unit tests.
This does not replace production or mapped/hardware evidence.

```sh
uv run --locked python study/protocol_exploration/build_usb_live.py
uv run --locked pytest -q test/test_usb_live_units.py
uv run --locked python study/protocol_exploration/run_usb_live.py usb_live --expanded-model
uv run --locked python study/protocol_exploration/run_call_legacy.py can_duplex --expanded-model

# Expected exit 1: 947 words exceeds the production 128-word capacity.
uv run --locked python study/protocol_exploration/run_usb_live.py usb_live
```

The response check uses the same USB 2.0 section 7.1.18.1 limits as the buffered
requirement: at least two bit times and at most 6.5 for a detachable device.
Source and measurement-boundary details remain in the
[baseline reference discussion](usb_receive_study.md#turnaround-failure).
These are digital-interface timings; transceiver delay, slew, pad behavior and
connector-level compliance remain unverified.

## Preliminary hardware cost

Paired unmapped core synthesis with the same YoWASP Yosys 0.55 method reports
40,510 generic cells for the call model versus 40,452 for the previous frontier:
58 extra generic cells, including ten return-address flip-flops. The program
array remains 18,432 enabled flip-flops; production uses 2,048. These are neither
mapped standard-cell counts nor area, timing, power or tile-fit results.

```sh
python3 study/protocol_exploration/synth_call_frontier.py
```

The production core and recorded physical-source hashes remain unchanged.
Storage architecture and full Tiny Tapeout implementation/signoff are still
needed before production adoption. The schedule assumes this model's memory,
fetch and branch latencies; an SRAM or pipelined fetch must preserve or rebudget
them. The next protocol milestone is addressed
token handling followed by endpoint-zero enumeration and control OUT/IN, while
preserving the successful packet timing and previous failing baselines.
