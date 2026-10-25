# Generic carry operations and addressed USB OUT/SETUP

2026-10-25. This follow-up demonstrates **addressed OUT and SETUP reception**
with firmware CRC5/CRC16 and timed ACK on an isolated generic CPU model. It
is not an enumerating USB device. All protocol state and calculations remain
assembly instructions; production RTL and its 128-word store are unchanged.

The frozen [947-word packet experiment](usb_live_study.md) remains reproducible,
as do the [buffered deadline failures](usb_receive_study.md). The new receiver
uses 310 words. Adding an addressed token gate takes 403 words. Both run only on
the explicit 1024×18/eight-register model with leaf calls and generic carry.

## Generic architectural experiment

[generic_carry_frontier.py](../study/protocol_exploration/generic_carry_frontier.py)
wraps the frozen call model with one carry flag and three ordinary CPU operations:

| Instruction | Semantics | Encoding extension |
|---|---|---|
| `SHRC rd` | Logical right shift; C gets old bit 0 | Existing SHR with bit 17 set |
| `RRC rd` | Right shift with old C into bit 7; C gets old bit 0 | Existing ROR with bit 17 set |
| `JNC target` | Branch when C is zero | Existing JFAIL with operand-A bit 0 set |

Carry resets on reset and configuration exit. The existing condition flag is
independent. Ordinary shifts preserve carry; legacy assembler-generated words
retain their original meaning. CALL/RET still has only one return address and
cannot nest. No polynomial, packet type or protocol mode exists in this RTL.
Carry propagation also serves ordinary multi-byte shifts and arithmetic.

Software CRC16 can now shift two bytes and conditionally XOR its polynomial in
six balanced cycles. A shared leaf routine performs NRZI decoding, stuffing,
byte assembly and CRC, replacing 24 unrolled kernels with three phase samplers.
The sampled period remains 33/33/34 clocks at 50 MHz. A normal bit routine takes
19 cycles including RET; a stuffed bit takes 11. A completed-byte path takes
31 clocks before its final schedule padding/jump. This reduces the packet image
from 947 to 310 words and leaves room for transaction state.

Paired core-only `synth -noabc` reports 5,647 production cells and 40,545 carry
model cells, compared with 40,510 for the frozen leaf-call model: **35 additional
unmapped generic cells**. These are not technology area, timing or fit results.
The much larger program flip-flop array remains the principal storage concern.

## Addressed transaction behavior

[build_usb_out.py](../study/protocol_exploration/build_usb_out.py) generates the
[403-word image](../study/protocol_exploration/usb_out_candidate.asm). Before
arming, firmware calculates CRC5 for the configured seven-bit address and
four-bit endpoint, using an 11-bit reflected polynomial loop. Comparing the two
received token bytes against this result validates destination and CRC5 together.
The host supplies address and endpoint, not a transaction checksum.

The program then:

1. Receives token packets with the same software NRZI/stuffing receiver.
2. Accepts exact OUT or SETUP PID and matching protected token body. Wrong
   destination or CRC5 clears the pending token and silently rearms.
3. Receives the following DATA0/DATA1 packet, including at a two-bit token-to-data
   gap measured from the token's SE0-to-J edge.
4. Checks PID, length, EOP and live CRC16. SETUP requires DATA0 and eight bytes.
5. ACKs a valid gated packet in the response window and returns its bytes and
   token PID through the existing generic runtime interface.

Orphan DATA is ignored. An intervening IN token clears a pending OUT gate;
this image does not respond to IN. Up to 15 detected packets may be processed
per request; detecting the 16th SOP ends the request with timeout status 6.
An idle wait also times out. Malformed DATA terminates with a local error and
no ACK; a subsequent runtime request can recover without reset or firmware reload.
This is a bounded exploration request, not an autonomous USB endpoint service.

## ABI and independent verification

Valid requests use operation 1, arguments address 0, arguments length 39,
input count 0 and output limit 11. Parameters are
`[ACK_enable, 36_static_CRC16_syndrome_bytes, address, endpoint]`.
The same payload-independent syndrome table is documented in the live packet
study. Address/endpoint are masked to seven/four bits. Full request validation
remains absent. The tests enable ACK and use valid envelopes.

On success, output entries contain PID, zero to eight arbitrary payload bytes,
and two received FCS bytes, with metadata zero. Event detail contains OUT's
0xe1 or SETUP's 0x2d. Error statuses preserve the packet probe conventions:
6 timeout, 16 CRC16, 17 framing/length, 18 unsupported PID, 19 stuffing,
20 overrun, 21 invalid DATA PID. Wrong destination/CRC5 tokens are ignored rather
than returned as errors. Private RAM 144–154 buffers the packet; 155–158 stores
expected token body, pending PID and bounded SOP count.

The [independent peer](../study/protocol_exploration/usb_out_peer.py) supplies
wire encoding and polynomial-division CRC5/CRC16. It observes ACK pins, bus
ownership and returned bytes; internal PC traces check sample spacing only.
It does not steer firmware or supply received checksums through the host API.
The boundary remains the selected TUSB1106 digital interface documented in the
packet study; no external packet controller is used.

Reproduce with Icarus and the locked Python environment:

```sh
uv run --locked pytest -q test/test_carry_frontier.py
uv run --locked python study/protocol_exploration/run_usb_dense.py usb_dense --expanded-model
uv run --locked python study/protocol_exploration/run_usb_out.py usb_out --expanded-model
uv run --locked python study/protocol_exploration/run_carry_legacy.py can_duplex --expanded-model
uv run --locked python study/protocol_exploration/synth_carry_frontier.py
```

The [evidence record](usb_out_results.json) preserves exact commands, source/XML
hashes, test counts, sweep measurements and synthesis results. Six compact-model
tests cover packet correctness/errors/deadlines, recovery, CALL banks and direct
carry semantics. Four transaction tests cover lengths 0–8, both DATA PIDs,
address/endpoint corners, SETUP, wrong destinations, all five corrupted CRC5
bits, orphan/intervening packets, minimum spacing, phase/rate variation, malformed
DATA, bounded ignored traffic and repeated requests. Three new unit tests check
fixed instruction encodings, legacy binary compatibility, operand boundaries,
generated-source freshness and rejection by the production assembler.

## Remaining work

- Implement arbitrary IN DATA transmission, CRC/stuffing and ACK/retry handling.
- Implement reset recognition, persistent endpoint/data-toggle state, duplicate
  suppression and endpoint-zero enumeration/control transfers. Receiving a SETUP
  packet does not execute its request or return a descriptor.
- Prove clock recovery/jitter tolerance beyond the tested five phases and
  ±1,000 ppm range; there is no within-packet resynchronization yet.
- Validate actual transceiver/pads/board behavior and mapped execution timing.
- Resolve production storage/encoding/area. The production core cannot execute
  this ISA or hold either image. A future SRAM fetch latency changes the budget.

The next USB task is a generic-instruction IN transmitter that returns an
arbitrary runtime payload after an addressed IN token, followed by independent
host ACK and retry tests. Enumeration and control state follow that packet path.
