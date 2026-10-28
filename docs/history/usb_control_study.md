> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# Live USB transmission and autonomous vendor control transfers

2026-10-25. A **648-word live transmitter** removes payload CRC/waveform
precomputation from the [629-word packet probe](usb_in_study.md). A separate
**776-word autonomous control image** uses it to execute a vendor control write,
IN status, vendor control read and OUT status under one runtime request. This
is progress toward endpoint-zero service, not USB enumeration. Production RTL,
ISA and physical results are unchanged.

## Live transmit firmware

[build_usb_stream.py](../study/protocol_exploration/build_usb_stream.py) builds
an image with the same request ABI as the preceding IN/OUT probe. Firmware
buffers only PID and up to eight payload bytes before arming. It computes
NRZI, stuffing and CRC16 as it transmits, then sends FCS and EOP. No per-payload
checksum or waveform is supplied by the host.

Two PID-dependent initial CRC constants compensate for processing PID in the
live CRC loop, leaving 0xffff at the first payload bit. They are 0xfe97 for
DATA0 and 0xfe1f for DATA1. The ordinary shift/XOR routine processes PID and
payload; it stops advancing CRC for FCS bytes. These are firmware initialization
constants, not protocol-aware hardware. A unit test compares the results against
the independent polynomial-division wire oracle for 1,800 arbitrary payloads.

The bit-preparation leaf routine costs 14 clocks including RET, and CALL adds
one. Transmit paths balance to 33/33/34 clocks at 50 MHz. The longest byte-fetch
path consumes 29 clocks before padding. Stuff bits do not advance byte/CRC state;
a required final CRC stuff bit is emitted before EOP. Only private RAM160–168
holds packet bytes, replacing the old 29-byte waveform plus stored FCS/encoder
state. The runtime-host test preparation interval falls from 200 to 10 µs;
this includes common request and token-CRC5 initialization, not just payload copy.
A five-microsecond initial request delay was too short for common initialization;
it is not the protocol's token-response deadline.

The six previous IN/OUT test groups pass on this image, including arbitrary
payloads, all-zero/all-one data, both PIDs, final stuffing, lost/malformed ACK,
phase/rate sweeps, minimum token-to-DATA gaps and alternating directions.
The frozen prepared-waveform and earlier packet studies remain reproducible.

## Autonomous control probe

[build_usb_control.py](../study/protocol_exploration/build_usb_control.py)
generates a separate image for **device address0, endpoint0** and payloads1–8
bytes. The runtime host submits one request and remains inactive until both
control transfers finish. An independent USB host then performs:

1. Vendor write SETUP: bmRequestType0x40, bRequest1, wValue/wIndex0, wLengthN.
2. OUT DATA1 with N arbitrary bytes, followed by device ACK.
3. IN zero-length DATA1 status, followed by host ACK.
4. Vendor read SETUP: bmRequestType0xc0, bRequest2, wValue/wIndex0, wLengthN.
5. IN DATA1 readback of those bytes, followed by host ACK.
6. OUT zero-length DATA1 status, followed by device ACK and runtime completion.

SETUP DATA0, CRC5/CRC16, data/status direction and expected DATA1 are checked in
firmware. Stored payload survives SETUP reception. A duplicate valid write DATA1
is ACKed and discarded while write status is pending. Lost IN ACK leaves the
sent state intact and a repeated IN returns identical data/status. Persistent
endpoint state is local to this bounded pair; a later runtime request starts a
new pair without firmware reload or reset.

The request uses operation1, arguments address0/length41, no input entries, and
output limitN. Arguments are the same static RX syndrome table envelope as the
packet probe: `[1, 36_syndrome_bytes, 0, 0, 0x4b, 0]`. On success, output contains
the N received USB bytes with metadata0. Errors return existing local statuses;
invalid data CRC produces16 with no USB ACK and a later request can recover.
Only valid command envelopes are supported; no general STALL/NAK policy exists.

Private RAM171 holds the transfer phase and a sent bit;172 holds saved length,
174 holds the expected write length, and182 holds current IN length. The SOP
budget permits31 processed packets and terminates on the32nd. Existing idle
waits are bounded. This is a finite service probe, not an indefinitely running
endpoint.

## Timing regression and verification

The control host uses a **2-bit token-to-DATA gap**, minimum2-bit IN-to-host-ACK
turnaround, and2.1-bit gaps between stages. The last margin covers the digital
resolver's10ns quantization. No runtime-host action occurs between stages.

The phase/rate test initially exposed missed DATA: token dispatch finished at
DATA SOP, and idle qualification missed the first SYNC cells. A PC trace located
the rearm boundary; dispatching OUT/SETUP first and shortening their address0
validation fixed the retained regression. A sent bit in the phase byte also
shortens the host-ACK path. This is a firmware scheduling fix; no protocol-specific
instruction or RTL engine was introduced. Address0 specialization is firmware
scope, and must be revisited when implementing SET_ADDRESS.

Reproduce with the locked Python environment and Icarus:

```sh
uv run --locked pytest -q test/test_usb_control_units.py
uv run --locked python study/protocol_exploration/run_usb_stream.py usb_stream --expanded-model
uv run --locked python study/protocol_exploration/run_usb_control.py usb_control --expanded-model
```

The [evidence snapshot](usb_control_results.json) records exact commands,
source/XML hashes, test names, latency samples and unchanged physical-source
hashes. Six live packet tests, three autonomous control tests and two new units
pass. Control tests cover varied payload lengths, zeros/ones, duplicate write,
lost status/read ACK, three phases across ±1,000ppm, CRC rejection and recovery.
The control phase/rate sweep measures2.129–3.979µs response latency across54
responses; the live packet IN sweep measures1.969–2.051µs across18 responses.
Wire expectations and CRCs are independent of firmware; traces only diagnose
failure and do not supply expected data or steer execution.

## Remaining gates

- Bus reset recognition and persistent device address/configuration state.
- Standard requests, descriptors, SET_ADDRESS status-ACK commit and enumeration.
- Multi-packet data-toggle sequencing and full duplicate/status retry handling;
  after final status ACK this bounded service publishes and stops listening.
- General request validation, STALL/NAK behavior and support beyond address0.
- Full jitter/clock recovery, mapped timing, physical fit and transceiver/board
  interoperability. The production128-word/four-register core cannot run these
  images; the generic carry/call model remains an isolated architectural study.

The next task is to extend the autonomous loop with reset and standard endpoint0
requests, then prove enumeration with an independent host. Live TX removes the
per-packet waveform preparation barrier, but does not close those state gates.
