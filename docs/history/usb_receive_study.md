> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# Low-speed USB packet reception and turnaround experiment

Follow-up: [live generic-ISA packet processing](usb_live_study.md) now meets the
packet-response window on an eight-register/leaf-call model. The buffered
images and failing deadline tests below remain unchanged baseline evidence.
The live result is not enumeration or an addressed control transfer.

2026-10-25. This is a packet-level feasibility study, **not an enumerating USB
device or a passing control transfer**. All packet work is generic-ISA firmware.
The production 128-word core is unchanged. A 400-word baseline and 391-word
firmware optimization are tested on explicit 512-word models only.

Five functional tests pass for each image: capture/NRZI/destuffing, DATA0/DATA1
validation, CRC16, malformed-packet recovery, clock variation, timeout and a
diagnostic ACK waveform. A separate USB turnaround requirement test fails for
both images. A valid eight-byte packet receives its diagnostic ACK about 140 µs
after EOP in the baseline and 126 µs in the optimized version. This is too late
for either detachable or captive-device response limits. Enlarging program
memory alone does not fix this buffered processing path.

## External interface

The selected experimental boundary is a **TI TUSB1106 transceiver**, not a USB
controller. SPEED and SUSPND are strapped low. The digital interface fits the
eight protocol pins:

| ASIC pin | TUSB1106 signal | Direction from ASIC |
|---|---|---|
| uio0 | VP, single-ended D+ receive | Input |
| uio1 | VM, single-ended D− receive | Input |
| uio2 | VPO | Output |
| uio3 | VMO | Output |
| uio4 | OE, active low | Output |
| uio5 | SOFTCON | Output |
| uio6..7 | Unused | Input |

The low-speed pull-up goes to D−. Board wiring must supply the transceiver,
its pull-up and required passives; no analog USB connection goes directly to
ASIC GPIO. In this model, VP/VM codes are J=2, K=1, SE0=0 and invalid=3.
OE high releases the bus. The transceiver model passes line levels only: it
does no packet detection, bit recovery, NRZI, stuffing, CRC or ACK generation.
Datasheet reference: [TI TUSB1106, tables 1–5](https://www.ti.com/document-viewer/TUSB1106/datasheet).

This is a documented interface selection. Actual pad timing, transceiver
propagation delay, slew, VBUS/attach behavior and board interoperability are
not validated. The model uses ideal line states with 10 ns digital update
granularity, followed by the existing core input synchronizers.

## Firmware contract and evidence boundary

Use a valid runtime request with operation=1, arguments_address=0,
arguments_length=1, no input bytes and output_limit=11. Argument 0 selects
passive reception (0) or the diagnostic ACK path (1). Firmware assumes this
envelope; it does not validate all request fields.

One request receives one isolated DATA0 or DATA1 packet with 0..8 payload bytes.
Successful output contains PID, payload and the two received CRC bytes;
metadata is zero. The terminal event echoes ID/epoch, has kind=1, consumes
zero input and reports 3..11 output bytes. Status 0 means this packet passed
validation; it is not USB transaction success.

| Status | Meaning |
|---|---|
| 0 | Packet validated |
| 6 | Initial idle/SOP polling expired |
| 16 | CRC16 residue mismatch |
| 17 | Invalid SYNC, SE1, EOP, alignment or short packet |
| 18 | PID outside the DATA0/DATA1 probe scope |
| 19 | Missing/invalid stuff bit, including a missing final stuff bit |
| 20 | Capture overflow or payload above the probe limit |
| 21 | PID nibble complement check failed |

Malformed packets return no data and do not trigger a diagnostic ACK. A later
request can succeed without reset or firmware reload. These are controlled
isolated-packet tests, not USB transaction retry/duplicate handling.

In diagnostic mode, firmware emits a constant ACK handshake packet only after
validating DATA. This measures waveform and latency. It does **not** first
validate an addressed OUT/SETUP token and must not be described as a USB
device response. No enumeration, token CRC5, address/configuration state,
endpoint-zero setup/data/status transfers, duplicate suppression or arbitrary
IN data transmission is implemented yet.

## What firmware does

[build_usb_rx.py](../study/protocol_exploration/build_usb_rx.py) emits the
[baseline assembly](../study/protocol_exploration/usb_rx_candidate.asm):

1. Arm after seeing idle J and detect SOP K; check the eight SYNC cells.
2. Capture each subsequent VP/VM line state into RAM until SE0. Check a second
   SE0 cell and the following J cell.
3. Decode NRZI and remove stuff bits from the captured states. Store decoded
   bytes behind the raw read cursor, reusing consumed buffer space.
4. Check byte alignment, length, PID complement and DATA0/DATA1 selection.
5. Compute reflected CRC16 over payload and received CRC, using generic shifts,
   masks and XORs; initial 0xffff, polynomial 0xa001 and expected residue 0xb001.
6. Optionally emit diagnostic ACK, then publish bytes and completion.

[build_usb_rx_compact.py](../study/protocol_exploration/build_usb_rx_compact.py)
tries a practical firmware optimization. Its
[391-word assembly](../study/protocol_exploration/usb_rx_compact_candidate.asm)
packs previous VP and the consecutive-one count in r2, leaving r3 for byte
assembly. It removes per-bit accumulator RAM spills. Capture, CRC and ACK are
otherwise unchanged. This improves latency but does not solve it.

No new opcode, USB RTL mode, CRC unit or fixed-function engine was introduced.
The builders emit only the generic instructions already available in the study
model. Production RTL and assembler remain unchanged.

| Resource | Baseline / compact |
|---|---|
| Program words | 400 / 391; production maximum 128 |
| Program model | Explicit 512 words and generic 9-bit address extension |
| Event | RAM128..143 |
| Raw line-state capture | RAM144..249, 106 slots |
| Decoded bytes | RAM144..154, reusing consumed raw space |
| State | RAM250..255; compact does not need252/255 during decode |
| Physical bit timing | Repeating 33/33/34 core clocks at 50 MHz |
| Capture trace intervals | 680/660/660 ns, starting at the third fractional phase |
| CRC | Offline, after capture and decoding |

There are only 33⅓ core cycles per low-speed bit. The current capture path
uses 8 issue/commit clocks before padding on each normal cell, so the study
does not prove that live processing is impossible. It proves that this buffered
decode/CRC schedule cannot meet response timing. A different firmware pipeline
could reuse the padding; register pressure, memory traffic and edge tracking
must be measured in that attempt before selecting generic architecture changes.

## Turnaround failure

USB 2.0 section 7.1.18.1 measures inter-packet delay from EOP's SE0→J transition
to the response J→K transition. Its device limits are 6.5 bit times for a
detachable cable and 7.5 for a captive cable: about 4.33 and 5 µs at low speed.
See the [USB 2.0 specification, section 7.1.18.1](https://sinelab.net/pdf/usb-20-specification.pdf)
(USB-IF-authored specification mirrored as a PDF; the
[official document page](https://www.usb.org/document-library/usb-20-specification)
links the current distribution).

The peer measures the digital boundary rather than connector analog timing.
The large measured miss remains a firmware blocker; these numbers cannot
certify a connector-level implementation.

| Payload bytes | Baseline ACK delay | Compact ACK delay |
|---|---:|---:|
| 0 | 34.481 µs | 30.401 µs |
| 1 | 46.763 µs | 41.298 µs |
| 8 | 139.613 µs | 125.776 µs |

These are the three functional-run samples; the standalone deadline reproducer
has slightly different host phase. Source-bound evidence and phase timings
are saved in [usb_receive_results.json](usb_receive_results.json). Instruction
observation records decode and CRC phase durations without steering the peer
or supplying expected packet contents.

## Reproduce and interpret tests

```sh
# Regenerate assembly; no protocol-aware hardware generation.
uv run --locked python study/protocol_exploration/build_usb_rx.py
uv run --locked python study/protocol_exploration/build_usb_rx_compact.py

# Each exits 1: 400/391 words exceeds production 128-word capacity.
uv run --locked python study/protocol_exploration/run_usb_rx.py usb_rx
uv run --locked python study/protocol_exploration/run_usb_rx_compact.py usb_rx_compact

# Five packet-level tests per image, explicit models only.
uv run --locked python study/protocol_exploration/run_usb_rx.py usb_rx --expanded-model
uv run --locked python study/protocol_exploration/run_usb_rx_compact.py usb_rx_compact --expanded-model

# Required deadline tests: both currently exit 1 with a turnaround assertion.
uv run --locked python study/protocol_exploration/run_usb_rx.py usb_rx --expanded-model --deadline-check
uv run --locked python study/protocol_exploration/run_usb_rx_compact.py usb_rx_compact --expanded-model --deadline-check
```

The five functional cases cover all lengths 0..8 and both DATA PIDs, zeros/ones
and seeded data; CRC/PID/stuff/SYNC/SE1/EOP/oversize/empty failures and recovery;
five SOP phases at relative rates -1000/0/+1000 ppm; diagnostic ACK encoding;
and no-SOP timeout followed by a good packet. The peer calculates CRC by
polynomial division, independently of firmware's two-byte LFSR, and checks the
known CRC16/USB check value for `123456789`. It observes fractional capture
intervals, output-enable ownership, decoded bytes, counts and empty runtime
state. The ACK waveform check does not assert a passing response deadline.

CI runs the functional cases separately from the production regression.
Dedicated failing deadline commands and their XML/evidence are preserved as
requirements, rather than weakening the allowed response time to pass tests.
Existing physical-source hashes remain unchanged; there is no new mapped,
expanded-model physical or hardware interoperability evidence.

## Next implementation task

The [live follow-up](usb_live_study.md) now moves NRZI/destuffing and CRC into
the receive schedule and meets the packet-response requirement on its model.
The buffered candidates below still fail unchanged. Keep both buffered variants for comparison. If a
live generic-ISA attempt cannot fit its cycle/register/memory budget, preserve
that failing attempt and propose the smallest reusable facility, with another
protocol use and physical cost. Larger storage, extra generic registers or
timed sampling are candidates, not selected fixes.

After packet timing works, implement token CRC5/address/endpoint matching,
reset, endpoint-zero enumeration and vendor OUT/IN exchanges with retries and
toggle state. The USB and nine-protocol bidirectional goals remain open.
