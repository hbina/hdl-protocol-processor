> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# Bidirectional USB packet firmware on the generic CPU model

2026-10-25. The **629-word image** adds addressed IN DATA transmission and host
ACK/retry handling to the [OUT/SETUP probe](usb_out_study.md). Both directions
use the same uploaded image and can alternate requests without reset. This is
packet/transaction evidence, not an enumerating USB device or production ASIC
support. No RTL changes or new instructions are needed for this follow-up.

## Firmware transmit path

[build_usb_in.py](../study/protocol_exploration/build_usb_in.py) generates the
[assembly](../study/protocol_exploration/usb_in_candidate.asm) from the frozen
403-word OUT image. The generic CALL/carry model remains unchanged.

Before arming for IN, firmware consumes the arbitrary runtime input payload,
calculates CRC16 using shifts/XORs, appends FCS, adds SYNC, performs NRZI encoding
and bit stuffing, and packs the resulting line states four per byte. It appends
two SE0 cells and a J cell for EOP. All this processing is ordinary assembly;
the host supplies neither FCS nor a line-state sequence.

The maximum eight-byte packet has at most 113 physical cells, including SYNC,
stuffing and EOP. The prepared waveform therefore occupies at most 29 bytes in
private RAM 192–220. RX storage 144–154 and runtime parameters remain intact.
Private RAM 159–170 stores SYNC, PID, payload and FCS; 181–185 holds waveform
count, request input count, encoder cursors and an awaiting-ACK flag. This leaves
the unchanged 256-byte runtime memory sufficient for this bounded experiment.

A matching CRC5-protected IN token starts a three-phase firmware output loop.
It loads and unpacks the states with generic instructions and drives the
transceiver at a fixed 33/33/34-clock schedule at 50 MHz. Byte-load paths are
balanced with NOP/WAIT. The final J cell lasts a full cell before OE is released.
Firmware then rearms the same software receiver for the host handshake.

An exact one-byte ACK PID with valid SYNC/stuffing/EOP completes an active IN
request. An ACK before any IN response is ignored. Without ACK, a repeated
matching IN token retransmits the prepared packet with identical PID, payload
and FCS. No toggle occurs before ACK. Idle timeout and the existing finite SOP
budget bound this experiment; there is no autonomous infinite retry loop.

## Runtime ABI

Use valid requests with operation 1, arguments address 0 and length 41. Parameters
are `[ACK_enable, 36_static_RX_syndromes, address, endpoint, IN_DATA_PID, direction]`.
The first 39 bytes preserve the OUT ABI. Direction 0 selects OUT/SETUP reception;
direction 1 selects IN. The IN PID must be DATA0 (0xc3) or DATA1 (0x4b).

For OUT, input count is zero and output limit is 11; results preserve the prior
probe contract. For IN, input count is 0–8 and input queue entries are the payload;
output limit is zero. Completion reports the number consumed, no output bytes,
and detail 0x69 after host ACK. Missing ACK eventually returns status 6. IN
payload/CRC bytes are checked by the independent wire peer, not echoed as runtime
output. The probe assumes valid request envelopes; complete shape validation
and draining invalid requests remain open.

The peer waits 200 µs after submitting IN before sending its token, allowing
firmware precomputation to finish. This is a documented preparation interval,
not the USB response time. A future autonomous endpoint must prepare its next
packet or be able to NAK while data is unavailable. Per-request host setup is
not fast enough to serve a complete control transfer by itself.

## Verification and reproduction

Use Icarus and the locked environment from the repository root:

```sh
uv run --locked pytest -q test/test_usb_in_units.py
uv run --locked python study/protocol_exploration/run_usb_in.py usb_in --expanded-model
```

The runner records source and XML hashes in
`test/sim_build/usb_in_carry_frontier1024/evidence.json`; the committed
[evidence snapshot](usb_in_results.json) also preserves timing samples. CI runs
this experiment separately from production and the earlier frozen USB studies.

The independent peer creates token CRC5 and expected DATA FCS with polynomial
long division. It checks every SYNC, data, stuff and EOP cell against the device
pins, verifies output release and bus ownership, measures token-to-DATA response
time, and sends host ACK at the minimum two-bit turnaround. It also checks TX
transition timing against the fractional clock schedule. The peer never reads
firmware waveform memory to decide what to expect.

Coverage includes arbitrary lengths 0–8, both DATA PIDs, all-zero/all-one payloads,
repeat IN after lost or malformed ACK, a mandatory final CRC stuff bit,
orphan ACK silence, wrong address/endpoint/CRC5 silence, five phases across
±1,000 ppm, missing-ACK timeout/recovery, and alternating IN/OUT/SETUP requests
on one image. The four prior OUT/SETUP test groups run again on the combined
image, including minimum token-to-DATA spacing. Source generation/capacity and
packed-storage bounds have two additional unit tests.

## Remaining USB acceptance gates

- Persistent endpoint-zero control sequencing, descriptors, SET_ADDRESS and
  SET_CONFIGURATION, and an independent enumeration demonstration.
- Bus reset recognition, endpoint/data-toggle state, duplicate OUT suppression,
  USB status-stage behavior, STALL/NAK policy and complete request validation.
- Endpoint service without a host preparation interval between every request.
- Full jitter tolerance and within-packet resynchronization beyond this tested
  phase/rate envelope.
- Production encoding/storage, mapped timing, physical fit and real-transceiver
  interoperability. The production 128-word/four-register core cannot load this
  image; earlier capacity and physical limitations remain unresolved.

The next task is an autonomous firmware endpoint-zero loop: receive SETUP,
interpret a small standard request set, transmit descriptors/status, and change
address only after the SET_ADDRESS status ACK. Reset and toggle/retry state must
be part of that loop rather than provided by runtime orchestration.
