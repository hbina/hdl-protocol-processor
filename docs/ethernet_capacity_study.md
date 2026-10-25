# Minimum-frame Ethernet: capacity and timing experiment

Date: 2026-10-25. **This 280-word image cannot load on the 128-word ASIC.**
It is tested on an isolated 512-word model with generic nine-bit long branch
addresses. Production RTL, instruction encoding, capabilities, and physical
results remain unchanged. A larger physical implementation has not been built.

The experiment implements valid minimum-sized Ethernet frame TX/RX through a
serial PHY interface, with FCS generated/checked in generic-ISA firmware.
It shows a useful bounded alternative to computing CRC while servicing each
incoming bit: capture one frame, then calculate CRC offline. It does not
demonstrate sustained 10 Mbit/s reception or complete Ethernet support.

## Scope and PHY boundary

The selected boundary is a preconfigured 10 Mbit full-duplex SNI PHY:

| uio | Signal | Direction |
|---|---|---|
| 0 | TXD | ASIC output |
| 1 | TX_EN | ASIC output during TX; otherwise released with external pull-down |
| 2 | TX_CLK | PHY input to ASIC, 10 MHz |
| 3 | RXD | PHY input to ASIC |
| 4 | RX_CLK | PHY input to ASIC, approximately 10 MHz |
| 5 | CRS | PHY input to ASIC, receive-valid/carrier indication |
| 6..7 | Reserved for optional management | Unused in this image |

Line coding, copper signaling, link pulses, and clock recovery are external.
Preamble/SFD transmission, serialization, frame buffering, FCS, and receive
decisions execute in firmware. No external MAC/controller or host-generated
FCS/waveform is used. MDIO configuration, PHY reset/straps, voltage levels,
pull-down sizing and the board itself remain integration work.

SNI is part-specific, so this is a digital interface experiment rather than
a claim of interoperability with a selected board. The timing checks use the
[TI DP83848C/I/VYB/YB datasheet](https://www.ti.com/lit/ds/symlink/dp83848c.pdf),
sections 5.6 and 6.4.4: serial clocks, a 20..30 ns TX high pulse with 70..80 ns
low, and a 25 ns TXD/TX_EN setup requirement. The peer tests this TX duty range;
RX uses nominal 50% duty and updates data on falling edges. RX duty extremes,
data/clock skew, clock-source switching and physical pad timing are unverified.

## Valid-request ABI

The image is [ordinary assembly](../study/protocol_exploration/ethernet_candidate.asm).
Parameter byte zero selects TX=0 or RX=1. Use a standard operation-1 request
with arguments_address zero and arguments_length one.

- TX supplies exactly 60 bytes: destination/source/type plus a 46-byte
  payload/padding area. It produces no output. Firmware prepends seven 0x55
  bytes and 0xd5, computes and appends four FCS bytes, then transmits 72 bytes.
- RX supplies no input and allows 64 output entries. Firmware finds SFD,
  captures the next 64 bytes and checks FCS. It returns the complete frame,
  including four checked FCS bytes, with zero metadata.

```python
request = Request(id, 1, arguments_length=1, input_count=60, output_limit=0)
await controller.submit(request, frame_body, b"\x00")
_, completion = await controller.complete(request)

request = Request(id + 1, 1, arguments_length=1, output_limit=64)
await controller.submit(request, b"", b"\x01")
output, completion = await controller.complete(request)
```

The image consumes but does not validate request operation, flags, reserved
fields, argument layout or declared counts. Callers must supply valid shapes
and initialized parameters. Invalid TX lengths can leave input undrained or
read unavailable bytes; this is not a hardened host API.

Completion preserves request ID and reports consumed input and produced
output counts, zero detail/reserved fields. Firmware statuses are 0=OK,
6=missing carrier/receive clock/SFD, 16=bad FCS, 17=carrier still high after
the minimum-frame capture. Rejected receive frames produce no payload.
Separate requests repeat without resetting or reloading the image.

No ARP/IP/UDP/TCP, VLANs, address filtering, half-duplex collisions, longer
frames, simultaneous TX/RX, or continuous unsolicited reception is claimed.
The host explicitly arms one receive request. Traffic during offline CRC or
runtime result handling can be lost; the peer waits for a new request window.

## How the bit budget is met

At 50 MHz the core has five cycles per serial bit, or forty per byte.
Instruction execution is single-cycle except two-cycle RAM/peripheral access.

TX precomputes the entire wire packet in RAM. The unrolled serializer shifts
one bit every five cycles. At the end of each byte it uses the remaining
slots to fetch the next byte, increment the pointer and decrement the byte
counter. External TX_CLK establishes initial phase; it is not polled for
every bit. The peer samples on the PHY's clock, not an instruction trace.

RX aligns to the receive clock, searches a sliding register for SFD and then
captures a fixed frame. The SFD loop samples every five cycles. Its compare,
countdown and conditional branches also bound a missing-SFD search without
changing the steady sample interval. In the byte loop, the first two samples
are four cycles apart, subsequent samples five apart; the shortened interval
leaves slots for the two-cycle byte store, pointer increment and counter.
The complete byte loop is exactly forty clocks. This intentionally moves
sample phase within a bit window and relies on the tested near-5:1 clock ratio.

The peer checks fifteen receive combinations: five phase offsets across one
20 ns core period and relative frequencies -100/0/+100 ppm. This is measured
digital coverage for a bounded frame, not a continuous clock-recovery proof.

After capture, firmware calculates reflected CRC-32 using four ordinary
8-bit RAM bytes, shifts, rotates, masks and XORs. TX initializes to 0xffffffff
and complements the final state before emitting little-endian FCS. RX checks
the pre-complement residue 0xdebb20e3 across the 64 frame bytes. The independent
peer uses Python zlib for FCS, so it does not share the firmware's CRC loop.
Offline processing means line rate and request throughput are different.

## Errors discovered and fixed

The first ideal-clock test used equal TX high/low periods and decoded frames
correctly. Adding datasheet-shaped clock pulses and setup assertions exposed
an alignment error: TX_EN could change only 3 ps before a sampling edge;
an intermediate fix left just 20 ns for TXD. Both violate the modeled 25 ns
requirement.

Firmware now preloads the first data bit while TX_EN is released, waits for
the observed clock transition and delays into a safe start phase before
enabling the PHY. The regression tests first-bit contents, complete packet
contents, TXD/TX_EN setup and interframe gap across five phase offsets and
20/25/30 ns high pulses. This fixes the modeled failure; actual pad delay and
board timing still need signoff.

Carrier acquisition initially slept for approximately five microseconds per
poll. It now polls every four clocks, with a bounded two-byte software counter,
so it can acquire a shortened preamble rather than miss SFD. Tests include a
receive packet with just one preamble byte before SFD.

## Bounds and remaining limitations

- Carrier wait is at most 65536 polls, approximately 5.25 ms plus publication
  overhead. Receive clock alignment has bounded low/high waits; SFD search is
  bounded to 256 sample attempts. Permanent low/high RX clocks return status 6.
- After capturing 64 bytes, the image waits briefly and samples CRS to reject
  an unsupported length. The peer asserts CRS over the serial packet exactly.
  Actual PHY carrier deassertion relative to the last serial data bit, including
  any delayed carrier tail, is an unresolved integration assumption; the guard
  must be validated before using a real PHY.
- Short/truncated test packets fail FCS. Firmware does not record CRS validity
  per bit or independently count the true frame length. Adversarial truncated
  frames with crafted tails are not covered by this simple length/FCS policy.
- Missing TX_CLK can still block the two initial WAITPIN instructions. A TX
  clock-loss watchdog and mid-frame reset/pause behavior are not implemented.
- RX assumes nominal clock duty and zero data-to-falling-clock skew. The PHY's
  full permitted RX timing envelope is not established by these tests.
- Core enable stays asserted through a burst. Runtime polling cannot stall
  firmware; this fixed-latency arbitration property matters to the byte loops.

## Resource and model evidence

| Resource | Result |
|---|---|
| Firmware | 280 words; actual assembler rejects at 128, and it also exceeds the earlier 256-word study size |
| Runtime | Existing one-outstanding-request, 64-byte input/output queues |
| RAM buffer | 160..231: eight TX prefix bytes plus one 64-byte frame |
| Scratch span | 144..240, 97 allocated bytes (96 used; byte 238 unused) |
| CRC state | Four ordinary bytes at 232..235; no hardware CRC unit |
| Model | 512-word memory, nine-bit PC/loader and generic long-branch extension only |
| Physical fit | Not measured; 512 words adds 6144 instruction-storage bits versus the current core, plus addressing logic |

The [study runner](../study/protocol_exploration/run_wave_c.py) generates a
separate core copy and isolated assembler module. JMP/JFAIL use an otherwise
unused operand bit for address bit eight; JZ/DJNZ use their unused high operand
bit. These are generic address extensions, not protocol instructions. A
public-pin diagnostic tests high-bank unconditional/conditional jumps,
decrement branches, loader access and the final word at address 511. Production
sources and their 128-word capability register are untouched.

The candidate is 152 words over actual capacity. This is a failure of this
implementation to fit, not a minimum-size proof or a decision to adopt 512
words. Code-density improvements, generic control flow and SRAM-backed storage
remain options after CAN and USB experiments. No new synthesis, PnR, mapped
simulation or hardware interoperability result is claimed.

## Reproduce

Actual capacity, **expected exit 1**:

```sh
uv run --locked python study/protocol_exploration/run_wave_c.py ethernet
```

Explicit counterfactual model:

```sh
uv run --locked python study/protocol_exploration/run_wave_c.py ethernet --expanded-model
```

Six tests in [the independent PHY peer](../study/protocol_exploration/ethernet_peer.py)
cover generic wide addressing; repeated minimum-frame TX/RX with independently
generated payloads/FCS; corruption, truncation, runt and unsupported length;
missing carrier/SFD and shortened preamble; fifteen RX phase/frequency cases;
missing RX clocks and recovery; and fifteen TX phase/duty/setup cases.

The [evidence record](ethernet_capacity_results.json) stores actual outcomes,
source hashes and the assembly rejection. Generated files live under
`test/sim_build/ethernet_capacity512/`. The explicit CI experiment is separate
from the production RTL regression. Current production sources still match
their historical physical baseline; none of this proves a larger core meets
the 50 MHz physical clock constraint.
