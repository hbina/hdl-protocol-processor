> Historical material for retired processor/runtime architectures. It is not
> verification evidence for combhdl. Recover processor sources at
> `d3886c6a364637cd736de369a004ac2693e559e2`.

# Minimal USB enumeration in generic firmware

2026-10-25. A **1,012-word firmware image** demonstrates a selected low-speed
USB enumeration sequence and arbitrary vendor control write/readback on the
isolated generic CALL/carry model. No RTL or ISA feature is added. This is
functional simulation evidence, not production ASIC support, full USB request
coverage, certification or host-OS interoperability.

## Device and host sequence

The device exposes EP0 with an eight-byte maximum packet and a single
vendor-specific interface using no additional endpoints. Endpoint-zero-only
interfaces are described in the primary
[USB interface descriptor definition](https://ieeemilestones.ethw.org/w/images/4/44/USB_1.0_Specification.pdf).
The test identity VID0xdead/PID0xbeef is a simulation fixture, not an assigned
hardware identity. String indexes are zero. The descriptor table contains an
18-byte device descriptor and an18-byte configuration/interface tree.

The independent host performs the usual descriptor/address/configuration stages
outlined in [Microchip's enumeration guidance](https://developerhelp.microchip.com/xwiki/bin/view/applications/usb/power-delivery/enumeration/):

1. Assert SE0 for10 ms and allow10 ms recovery.
2. Request the first eight device-descriptor bytes at address0.
3. SET_ADDRESS37, including a lost status ACK/retry, then use address37.
4. Read the full device descriptor in DATA1/DATA0/DATA1 chunks of8/8/2 bytes.
5. Read the configuration header, then its complete18-byte descriptor tree.
6. SET_CONFIGURATION1 and read GET_CONFIGURATION to verify the value.
7. Exchange an arbitrary eight-byte vendor control write and readback, including
   both status directions, before publishing one runtime completion.

Every packet, CRC, stuffing rule, DATA toggle, setup dispatch, retry decision,
address/configuration update and endpoint phase remains assembly instructions.
The runtime host loads firmware data before starting and takes no action during
these USB stages. The independent wire host checks expected bytes and CRC with
its own literal descriptors and polynomial-division oracle. It does not read
firmware memory to derive expected responses.

## ABI, data and implemented request scope

The [builder](../study/protocol_exploration/build_usb_enum.py) generates the
[assembly](../study/protocol_exploration/usb_enum_candidate.asm) and
[constant descriptor data](../study/protocol_exploration/usb_enum_constants.json).
Valid requests use operation1, arguments address0/length77, input count0 and
output limit equal to the later vendor payload length1–8. The first41 argument
bytes preserve the preceding probe envelope; bytes41–58 hold the device
and59–76 hold the configuration descriptor. These are constant firmware data,
not precomputed line states or transaction checksums.

Implemented standard requests are SET_ADDRESS, GET_DESCRIPTOR for device and
configuration index0, SET_CONFIGURATION0/1, and GET_CONFIGURATION. Descriptor
length is capped to18 bytes; reads of8,9,18 and255 bytes are tested. A requested
length0, unsupported descriptor/string/class requests and general malformed
request behavior are outside the demonstrated request envelope. This is not
a complete Chapter9 implementation; general STALL/NAK handling remains absent.

Descriptor data is streamed directly from read-only parameter RAM. Private
RAM181 holds source pointer minus1,182 current packet length,187 remaining
bytes,188 current configuration,189 pending configuration, and190 standard-read
mode. DATA PID is at160; staged next-packet metadata occupies192–195. SETUP
resets the first DATA PID to DATA1. Metadata advances only after valid host ACK;
lost ACK retries keep the pointer, count and PID. Reset clears configuration
alongside address/control state. Configuration and address commit share the
standard-write status-ACK path.

The finite service permits127 processed packets and times out on the128th SOP.
It still returns to the runtime host after the selected vendor write/read pair;
it is not indefinite device service across runtime requests.

## Capacity and firmware scheduling

The 921-word reset/address image left103 words. Removing unreachable packet
preparation/dispatch, a redundant DATA PID-complement check, unused input-count
capture, and variable initial-address CRC setup recovered room. The device
always initializes at address0; dynamic SET_ADDRESS remains supported.
Production capacity is still128 words and four registers. The model still needs
1,024×18 program bits, eight registers, generic carry and a single return address.

The first enumeration candidate used991 words and passed longer-gap descriptor
transfers, but missed the next IN at a short host gap after descriptor ACK.
The retained [991-word candidate](../study/protocol_exploration/usb_enum_unoptimized_candidate.asm)
and failure command below preserve this scheduling blocker.

The fixed image stages the next pointer/count/remaining bytes/PID during the
first SYNC cell, using31 of its32 available post-output clocks. Six metadata
loads fit into existing ACK EOP padding, while non-ACK paths retain token-address
prefetch and live RX CRC state. A fast one-byte-handshake path commits the staged
metadata only after valid PID/length/EOP. These are ordinary LOAD/STORE/branch
instructions scheduled in existing wait slots. The wire sample/output cadence
remains33/33/34 clocks; neither buffering nor an external controller performs
protocol work.

## Verification and reproduction

```sh
uv run --locked pytest -q test/test_usb_enum_units.py
uv run --locked python study/protocol_exploration/run_usb_enum.py usb_enum --expanded-model
# Expected failure: retained slower ACK bookkeeping misses the next IN.
uv run --locked python study/protocol_exploration/run_usb_enum.py usb_enum --expanded-model --unoptimized-ack --test-filter test_descriptor_short_interpacket_gap
```

The [evidence snapshot](usb_enumeration_results.json) records commands,
source/XML hashes, passing cases, timing samples and the expected failing
comparison. The production physical-source hashes are unchanged. Two new
unit tests validate descriptor layout/data and both generated programs/capacity.
The full enumeration trace has 38 timed device responses at 2.113–3.787 µs.
The descriptor phase/rate test records 185 responses at 2.100–3.467 µs, including
its configuration commit/reset checks. All stay in the tested response window.

Ten model groups cover the six previous control/reset/address regressions,
descriptor/configuration reads, full enumeration plus vendor traffic, short
interpacket gaps, and a three-phase×three-rate descriptor sweep. Retries include
every descriptor chunk, configuration status and address status. An interrupted,
unACKed SET_CONFIGURATION is followed by GET_CONFIGURATION0; successful commit
returns1 and reset restores0. Token-to-DATA gaps remain two bits and the short
interstage checks use2.1 bits; general full USB jitter tolerance remains unproven.

## Remaining limits

- Twelve instruction words remain in this model. Further validation, request
  modes and error responses need another code-density or storage assessment.
- Only the selected standard/vendor requests and finite service are covered;
  no OS interoperability, full status retry service after publication, suspend/
  resume policy, general STALL/NAK handling or reset-during-active-TX proof.
- Full input jitter/within-packet clock recovery, pad/transceiver/connector
  behavior and electrical USB compliance remain unverified.
- The production core cannot execute this image. Generic-model synthesis and
  storage estimates do not establish mapped timing, area, tile fit or signoff.
  Earlier buffered response failures and production capacity blockers remain.

The next project task is to audit all nine experiments against their original
minimum TX/RX contracts and resource evidence, then prioritize the generic
production storage/execution changes and any remaining functional blockers.
