> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# USB bus reset and deferred SET_ADDRESS in generic firmware

2026-10-25. The **921-word image** extends the autonomous vendor-control probe
with bus-reset qualification, address changes, and continued control transfers
at a new address. All behavior is generic-ISA firmware on the isolated
1024×18/eight-register CALL/carry model. Production RTL and physical results
are unchanged. This is not an enumeration demonstration.

## Reset and address behavior

A host reset holds both USB lines low (SE0); the host maintains it for 10 ms,
while a device may detect sustained SE0 earlier. See Microchip's primary
[reset signaling guidance](https://developerhelp.microchip.com/xwiki/bin/view/applications/usb/how-it-works/reset-suspend-resume/).
The firmware qualifies SE0 with 40 consecutive four-clock samples, approximately
3.2 µs plus input-synchronizer and entry latency. A short pulse returns to idle
qualification and preserves control/address state.

A qualified reset releases the output driver and clears current/pending address,
pending token, transfer phase/sent state, saved payload length and IN count. It
restores the address-zero token CRC5 and finite SOP/idle budgets, waits for SE0
to end, then rearms. It does not toggle rst_n, reload firmware, clear the runtime
request, or publish a completion. The same runtime service can continue after
reset. Reset is checked while waiting for traffic and from malformed-frame
handling, allowing an unfinished RX packet to be abandoned. Reset during active
TX is not covered by this electrical peer model.

Firmware recognizes the standard SET_ADDRESS SETUP envelope: bmRequestType=0,
bRequest=5, wValue=0–127, wIndex=0, wLength=0. It sends zero-length DATA1 status
at the current address. The address changes only after the host ACKs that status,
as required by [USB section 9.4.6](https://ethw.org/w/images/4/44/USB_1.0_Specification.pdf).
A lost ACK leaves the pending address uncommitted and repeated IN at the old
address returns the same status. A reset cancels the pending change.

The new token CRC5 is calculated before status transmission with seven
conditional XOR contributions for address bits. These are firmware constants
for the CRC5 polynomial, not an RTL CRC unit or host-supplied transaction checksum.
Two unit tests check generated source/capacity and the XOR basis for all 128
addresses against the independent polynomial-division token oracle.

## Timing and memory

Dynamic address matching must preserve the two-bit token-to-DATA gap. The
firmware prefetches the expected address during existing EOP waiting time,
then compares the received low token byte against it. The high-byte comparison
still checks endpoint-zero bits and CRC5. The same padding replenishes the
idle counter. Replacing part of WAIT with ordinary LOAD/STORE instructions keeps
the EOP sample schedule unchanged and avoids adding work after a token.

Private RAM155/156 holds current token body;175/176 holds pending address and
CRC5 byte;186 holds a four-period idle budget. The normal idle polling budget
is approximately 31 ms at 50 MHz, sufficient for the tested 10 ms post-reset
recovery. Sustained reset waits for release without consuming that budget.
The original finite SOP limit remains: 31 processed packets, timeout on the32nd.

The request and vendor command ABI otherwise match the
[autonomous control study](usb_control_study.md): one runtime request spans
SET_ADDRESS/reset activity and the vendor write/status/read/status pair.
Initial parameters select address0/endpoint0. Runtime output remains the
arbitrary vendor payload received over USB. A new runtime request initializes
a new bounded service; this is not indefinite device service across requests.

## Verification and reproduction

```sh
uv run --locked pytest -q test/test_usb_address_units.py
uv run --locked python study/protocol_exploration/run_usb_address.py usb_address --expanded-model
```

The [evidence snapshot](usb_address_results.json) preserves exact commands,
source/XML hashes, latency samples and unchanged physical-source hashes.
Six model test groups pass:

- The three previous autonomous-control groups, including timing/retry and
  CRC-error recovery, rerun on the new image.
- Deferred address commit, lost status ACK, silence at the pending/old address,
  a full 10 ms reset plus 10 ms recovery, then address127 and vendor readback.
- Short-SE0 rejection, cancellation of an unACKed pending address, reset after
  a partial incoming packet, and subsequent successful control exchange.
- Addresses1/37/127 with three paired phase/rate settings each, followed by
  arbitrary eight-byte vendor write/readback. These are nine cases, not the
  full address×phase×rate Cartesian product. The retained address-zero control
  sweep separately covers three phases across −1,000/0/+1,000 ppm.

The address sweep has 72 timed responses, measuring 2.077–3.993 µs; the retained
control sweep has54 responses at 2.069–3.999 µs. Both stay within the tested
1.33–4.33 µs response window. Token-to-DATA gaps remain two bits and control
interstage gaps2.1 bits. Wrong-address probes use an additional observation
interval; no minimum SET_ADDRESS-status-to-new-SETUP claim is made.

The independent host checks wire encoding, CRC, ACK timing and returned bytes.
It supplies no transaction checksums via the runtime interface. The reset test
uses real wire SE0 and a full10 ms hold; the separate20 µs pulses exercise filter
and partial-packet behavior without replacing that full-duration test.

## Remaining enumeration and implementation gates

- GET_DESCRIPTOR with device/configuration descriptors, multi-packet DATA toggle
  sequencing, SET_CONFIGURATION and an independent enumeration sequence.
- General request/STALL/NAK policy and full endpoint/status retry service.
- Idle/suspend/resume behavior beyond this finite request service, reset during
  active TX, complete jitter/clock recovery and hardware interoperability.
- Production capacity, encoding/storage, mapped execution timing and physical
  fit. The production128-word/four-register core cannot execute this image.

The model has only103 instruction words left. The next task is to implement
standard descriptor/configuration handling, remove unreachable probe code as
needed, and measure whether a complete enumeration flow fits before considering
another generic storage change.
