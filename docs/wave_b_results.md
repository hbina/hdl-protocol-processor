# JTAG, SWD and PS/2 exploration

Date: 2026-10-24. Protocol behavior is entirely generic-ISA firmware. No
production RTL, instruction encoding or physical implementation has changed.
The [nine-protocol goal](protocol_exploration.md) remains open.

| Protocol | Firmware words | Execution evidence | Current limitation |
|---|---:|---|---|
| JTAG | 125 / 128 | Production RTL; independent TAP peer | Valid envelopes only; three spare words; mapped/hardware coverage pending |
| SWD | 230 / 128 | Two tests on explicit 256-word model | Actual assembler rejects image; production capacity unresolved |
| PS/2 | 188 / 128 | Two tests on explicit 256-word model | Actual assembler rejects image; production capacity unresolved |

The size failures are for these implementations, not minimum-size proofs.
Software compaction, reusable generic control flow and larger instruction
storage remain candidate solutions. The earlier [I2C study](i2c_capacity_study.md)
uses the same explicit larger-capacity model technique. A larger model passing
does not establish area, timing, pad behavior or physical signoff for that size.

## JTAG on the current core

Sources: [firmware](../firmware/jtag_probe.asm),
[independent TAP](../test/test_jtag_probe.py).

The image drives TCK=uio0, TMS=uio1, TDI=uio2 and samples TDO=uio3. Output enable
is 0x07. It sends five TMS-high clocks at boot to reset the TAP, enters
Run-Test/Idle, and preserves the target instruction between runtime requests.
For each request, firmware selects IR or DR, traverses Capture and Shift,
raises TMS on the final shifted bit, traverses Update, and returns to idle.
TCK has nominal five-microsecond half-cycle waits plus software overhead;
its rate is below 100 kHz at the modeled 50 MHz core clock.

### Valid-request ABI

```python
request = Request(
    id, 1, arguments_length=2, input_count=len(payload), output_limit=len(payload)
)
await controller.submit(request, payload, bytes([ir_scan, last_byte_bits]))
output, completion = await controller.complete(request)
```

Parameters are at address zero: ir_scan is 0 for DR or 1 for IR;
last_byte_bits is 1..8. Payload length is 1..64 bytes. Scan length is
`8 * (len(payload) - 1) + last_byte_bits`, from 1 to 512 bits. Input is packed
LSB first; unused high bits of the last input byte are ignored. Output is
LSB first for complete bytes; a partial final byte is shifted into its high
bits, with zero low padding. Metadata is zero. The host knows valid final
bits from its request and can shift that last byte down before unpacking.

The image returns the request ID, consumed input count, produced output count,
status zero, zero detail and reserved fields. It consumes but does not validate
the operation, envelope or arguments. Incorrect shapes can corrupt TAP state
or fail to complete; this is a valid-request probe, not a hardened interface.
Scratch spans 144..160 (17 bytes), with all four registers used. Resetting the
TAP between requests, chains of multiple TAPs, target-specific programming
algorithms, and configurable TCK rate are not implemented. Voltage compatibility
and optional level translation must be documented for a real target.

### Acceptance evidence

The peer implements all sixteen TAP states and separate capture/shift/update
register behavior. It begins in Pause-DR to exercise reset, drives TDO on
falling edges and samples TMS/TDI on rising edges. Its registers include
five-bit IR capture pattern 01, IDCODE, a 32-bit writable data register, and
one-bit BYPASS. These are test-target choices, not a fixed ASIC protocol block.

Tests check IDCODE, arbitrary IR selection with nonzero padding, DR lengths
1/7/8/9/31/32/33/511/512, independent target values, write/readback of 0xdeadbeef,
BYPASS and preserved instruction selection without reset/reload. Returned
bits are predicted from payload and target registers, not DUT instructions.
The peer checks at least 10 microseconds per TCK period, five-microsecond
high/low periods, TMS setup, pin direction and clock-high control stability.

The complete production RTL regression now contains ten tests: five baseline,
three UART, one SPI and one JTAG. New firmware has no mapped or hardware
coverage yet. JTAG signal/state references:
[AMD configuration guide, boundary scan chapter](https://www.amd.com/content/dam/xilinx/support/documents/user_guides/ug570-ultrascale-configuration.pdf).

## SWD capacity experiment

Sources: [firmware](../study/protocol_exploration/swd_candidate.asm),
[DP peer](../study/protocol_exploration/swd_peer.py).

SWCLK=uio0, SWDIO=uio1; the host drives clock and changes SWDIO direction.
Firmware sends 56 high line-reset clocks and idle clocks at boot. This scope
assumes a target already selected into SWD mode, one-cycle turnaround, DP
accesses only, and overrun data phases disabled. SWJ selection, AP accesses,
posted-read handling, multidrop, and alternate turnaround settings are deferred.

### Valid-request ABI and behavior

Parameters at address zero are `[RnW, address_index]`: RnW 1=read, 0=write;
address_index 0..3 selects DP address 0/4/8/12. Submit a standard request with
operation 1 and arguments_length two. A read has input_count zero and
output_limit four. A write prebuffers four little-endian bytes and has
output_limit zero. The image does not validate the envelope or arguments.

Firmware constructs Start/APnDP/RnW/address/parity/Stop/Park, releases the
wire for turnaround and ACK, and performs a 32-bit data phase plus even parity.
It shares the same generic bit loop between reading and writing; received
read bytes stay in scratch until parity is verified. A parity failure therefore
publishes no data. Reads return four bytes with zero metadata; writes return
none. Completion retains ID/counts and zero detail/reserved fields.

ACK WAIT retries at most three request attempts and does not pop write data
until ACK OK. Status 10 means WAIT exhausted, 11 FAULT or an unexpected ACK,
12 read-parity failure, and 0 success. Firmware performs the final turnaround
and eight idle-low clocks before completion. It does not automatically clear
a sticky FAULT: the controller can issue a DP ABORT write. Invalid ACK values
share the FAULT status; resynchronization after arbitrary malformed traffic is
not verified. Timeout/cancellation and mid-transfer reset coverage remain open.

Nominal half-cycle waits are five microseconds plus instruction overhead;
clock periods are at least ten microseconds. Scratch allocation spans 144..167
(24 bytes, including one unused byte); request attempts, parity, a pointer and
four data bytes accompany the 16-byte event. The image is 230 words, 102 over
the actual limit, with 26 spare words in the test model.

### Acceptance evidence

The independent peer validates request and data parity, bit order, full-cycle
turnaround and absence of SWDIO driver overlap. Its DP subset models IDCODE,
power request/acknowledgement bits in CTRL/STAT, SELECT writes, externally
prepared RDBUFF values and ABORT sticky-fault clearing. This is a wire-protocol
and selected-register test, not complete Arm debug-system verification.

Two tests cover repeated varied SELECT writes and RDBUFF reads, IDCODE,
CTRL/STAT, two WAITs then OK with exactly one write, WAIT exhaustion without
write-data loss, persistent FAULT, ABORT recovery, rejected read parity and
a subsequent successful read without resetting/reloading firmware. The peer
checks clock periods and direction ownership. Protocol reference:
[Arm IHI 0031G, SW-DP operation](https://documentation-service.arm.com/static/622222b2e6f58973271ebc21).

## PS/2 capacity experiment

Sources: [firmware](../study/protocol_exploration/ps2_candidate.asm),
[device peer and resolver](../study/protocol_exploration/ps2_peer.py).

Clock=uio0 and data=uio1 are open drain. uio2 is an additional push-pull
RX-armed indicator for the controller/test fixture; it is not a PS/2 signal.
The device supplies the clock in both directions. A real interface needs
pull-ups and suitable level translation for a 5 V peripheral. Digital simulation
does not establish pad compatibility, rise times or real-device behavior.

### Valid-request ABI and behavior

Submit operation 1, arguments_length one, parameter address zero containing
receive_count 0..64. The payload contains either zero or one arbitrary command
byte, with matching input_count. output_limit must cover receive_count. The
image does not validate that shape; multi-command input is outside its contract.
It transmits the optional command before receiving a bounded burst of bytes.

For TX, firmware inhibits clock for at least 120 microseconds, asserts data
for request-to-send and releases clock. It sends eight LSB-first bits, odd
parity and stop using device clock edges, then checks the device's separate
wire ACK. That ACK is distinct from a byte such as 0xFA sent afterward.
RX validates start, eight data bits, odd parity and stop, then returns the
byte with zero metadata. Previous valid bytes are preserved after a later error.
Request IDs, consumed counts, actual output counts and standard terminal events
allow repeated requests without reset/reload.

Status 6 means edge/idle timeout, 13 missing wire ACK, 14 bad start/stop,
15 parity failure, 0 success. Every polling wait has 256 attempts with a
256-cycle WAIT, approximately 1.33 milliseconds per edge. A missing peer or
stalled clock therefore completes with released protocol pins. This is a
poll-count bound, not a programmable clock-deadline service. After an error,
the peer must finish or release its faulty frame before the next exchange.

The RX indicator rises after the optional TX/link ACK and stays high through
the receive window. RX-only peers start after observing it. The command-response
peer starts independently after a released idle interval following wire ACK;
it does not wait for controller polling. Continuous unsolicited reception,
keyboard scan-code translation, application command policy and automatic
retransmission are outside the image. The 188-word candidate exceeds actual
capacity by 60 words. It uses 18 scratch bytes at 144..161.

### Acceptance evidence

The resolver combines independent host/device open-drain drivers and rejects
host logic-high drive. The device measures host inhibit, decodes TX at its
rising clock edges, validates odd parity/stop and supplies a separate wire ACK.
Device-originated frames are sampled by firmware on the low/falling phase.

Two tests cover repeated command/0xFA response exchanges with 0xed/0x07 and
0x00/0xff/0x55/0xaa data, arbitrary 64-byte reception, and 30/40/50-microsecond
half-periods (approximately 16.7/12.5/10 kHz). Failure cases include parity,
start and stop errors, no response, timeout between bytes with retained output,
missing wire ACK, missing device clocks, stalled low clock and later recovery.
The peer implements raw byte exchanges, not a complete keyboard command set.
Reference: [Microchip AVR313 timing and host commands](https://www.microchip.com/content/dam/mchp/documents/OTH/ApplicationNotes/ApplicationNotes/doc1235.pdf).

## Commands, evidence and next work

```sh
# Actual production RTL, including JTAG:
uv run --locked pytest -q test/test_assembler.py test/test_runtime_units.py test/test_runtime_driver.py
uv run --locked make -B -C test

# Expected exit 1: demonstrate the actual 128-word capacity failures:
uv run --locked python study/protocol_exploration/run_wave_b.py swd
uv run --locked python study/protocol_exploration/run_wave_b.py ps2

# Explicit larger-program models, not actual ASIC coverage:
uv run --locked python study/protocol_exploration/run_wave_b.py swd --expanded-model
uv run --locked python study/protocol_exploration/run_wave_b.py ps2 --expanded-model
```

The [machine-readable record](wave_b_results.json) contains actual outcomes,
commands and source hashes. Individual model runs produce evidence and XML
under their separate `test/sim_build/*_capacity256/` directories. CI is configured
to run the same explicit experiments separately from the production RTL suite.
The model helper changes only generated instruction-store/address/branch widths;
production capabilities still report 128 words and are not a 256-word board ABI.

The [Ethernet experiment](ethernet_capacity_study.md) now demonstrates bounded
minimum-frame TX/RX on a larger-program model. [CAN receive](can_receive_study.md)
now has live CRC/ACK evidence on that model; [CAN transmit](can_transmit_study.md)
passes separately. Combined-image capacity and remaining CAN node behavior stay
open. [USB packet reception](usb_receive_study.md) now has larger-model evidence
and reproduced timing/capacity failures; enumeration remains next. Completing
production capacity decisions, request validation, all remaining acceptance
tests, mapped verification and hardware interoperability remains separate work;
these valid-request probes do not close those requirements.
