# Firmware protocol probes

These exploratory images test the nine-protocol plan on the unchanged
128-word core. They are intermediate implementations, not substitutes for
the full acceptance contracts in [the exploration plan](protocol_exploration.md).
Protocol behavior executes exclusively in generic ISA instructions.

## UART probe

Sources: [firmware](../firmware/uart_probe.asm),
[independent pin peers](../test/test_uart_probe.py).

- Image size: 107 words, 21 free. Scratch use: 17 bytes (event at 144..159,
  receive count at 160). All four registers are used; no RTL changes.
- TX=uio0, RX=uio1. TX is idle high; output enable is exactly bit zero.
  Connect a logic-level peer at the correct I/O voltage. No external UART
  controller is assumed. Hardware interoperability has not been tested.
- 8N1, LSB first, nominal 115200 baud. The actual TX bit period is 434 core
  clocks at 50 MHz (8680 ns, approximately 115207 baud). Inter-frame idle can
  exceed one stop bit. No simultaneous TX/RX; all TX precedes RX.
- The host prebuffers 0..64 arbitrary TX bytes and requests 0..64 RX bytes.
  Firmware consumes the submission and returns matching request ID, input
  count, output entries with zero metadata, and a terminal event. Requests
  repeat without reset/reload.

### Probe ABI and limitations

Use `Request(id, op, arguments_length=4, input_count=len(tx),
output_limit=rx_count)` with arguments `bytes([rx_count, 1, 0, 0])` at address
zero. For valid requests choose op 1=TX, 2=RX, 3=TX_THEN_RX; this probe does
not inspect the operation or validate the envelope/argument layout. The
caller must supply correct counts, RX count <=64, enough output capacity,
and initialized parameter byte zero. Malformed-request handling remains
required for the final UART image. Values outside this contract may fail to
complete or drop outputs; do not use this probe as a hardened host API.

Poll diagnostic r3 at 0x010e for 0xA5 to observe RX arming, then wait two bit
periods before sending the response. In TX_THEN_RX the peer must wait for the
response window after TX. Traffic outside that window can be lost. The marker
is diagnostic firmware state; no protocol-aware hardware handshake was added.

Status 0=OK, 6=RX_TIMEOUT, 7=FRAMING_ERROR. Invalid-stop bytes are not published;
preceding valid bytes are retained. Received count reports actual published
bytes; input count includes all transmitted bytes. The probe accepts a low
line at arming as a possible start; unlike the final contract it does not
first require a high-to-low transition. A persistently low line yields a
framing failure after sampling one frame. A short false start returns to
the bounded search. After completion the next request can run without reset.

The timeout is **65536 polling attempts per next byte**, not the planned
timeout_windows clock deadline. Argument byte one is currently ignored.
Normal high-line polling uses four core cycles, plus one outer-counter
cycle per 256 polls; a quiet timeout is approximately 262400 clocks (5.25 ms)
before completion publication/host overhead. False-start qualification uses
additional cycles but still consumes a poll, so even a false-start flood
is finite. Static worst-path accounting bounds search below 288 ms, not the
65536-clock deadline in the final plan. That worst-case flood bound has not
been exhaustively simulated. Deadline accuracy and stuck-low rearming remain
work, not evidence of an ISA impossibility.

Static instruction accounting gives 434 clocks between RX bit samples and
29 clocks from a valid stop sample back to the next start-search sample when
another byte is requested. This leaves roughly 188 clocks before the next
start of a nominal back-to-back frame. The peer tests independently exercise
back-to-back frames and input clock/phase variation; the static count is not
a physical timing measurement.

### RTL coverage

The three tests cover:

- Repeated arbitrary TX/RX with lengths 0/1/2/63/64, explicit 0x00/0xff/0x55/
  0xaa TX patterns, independent reply data, and separate 64-byte TX-only and
  RX-only requests. The TX peer checks exact transition times as well as
  decoding data and stop bits.
- Fifteen combinations of five core-clock phase offsets and sender rate
  errors -1%, 0%, +1%, with back-to-back 0x00/0xff/0x55/0xaa frames.
- A false start, an invalid stop after a valid byte, no response, timeout
  between bytes, retained partial output, and a subsequent successful request.

Asynchronous host polling occurs while firmware runs. Reset during TX/RX,
malformed request validation, configurable baud/framing, and mapped/hardware
coverage of the new image remain unimplemented or unverified.

## SPI probe

Sources: [firmware](../firmware/spi_probe.asm),
[independent peripheral peer](../test/test_spi_probe.py).

- Image size: 72 words, 56 free. Scratch use: 17 bytes (event 144..159,
  remaining count 160). No RTL changes.
- Mode-0 controller, MSB first: uio0=CS_n, uio1=SCLK, uio2=MOSI,
  uio3=MISO. Output enable is exactly 0x07; idle output is 0x01.
- The host supplies 1..64 TX bytes; the peer simultaneously supplies the
  same number of independent RX bytes. CS stays low for the whole transfer.
  Requests repeat without reload/reset, with returned data, zero metadata,
  request ID, counts and a standard terminal event.
- SCLK rising edges are 500 core clocks apart inside each byte (100 kHz at
  50 MHz). High time is 248 clocks; low time is 252 inside a byte. There is
  an additional documented inter-byte gap while servicing queues/counters.

### Probe ABI and limitations

Use `Request(id, 1, input_count=len(tx), output_limit=len(tx))` with no
arguments. The probe consumes but does not validate operation, argument,
reserved fields or requested lengths. Actual input FIFO occupancy determines
the transfer length. The caller must provide a valid 1..64 byte request and
sufficient output capacity. Empty input currently completes as a no-op.
Firmware does not detect an absent peripheral: SPI has no mandatory ACK, so
an undriven MISO needs a defined external bias and will simply be sampled.

Tests perform eight repeated transactions of lengths 1/2/63/64 with different
seeded payload/reply data. The peer checks bit order, exact intrabyte SCLK
period and high time, MOSI stability while SCLK is high, CS framing, pin
directions, and returned bytes. Clock rate, SPI modes 1–3, malformed requests,
and broader peripheral compatibility are not implemented. No mapped or
hardware evidence is claimed for this image.

## Reproduction and evidence

Icarus 12.0, cocotb 2.0.1, Python 3.12.4, locked dependencies:

```sh
uv run --locked pytest -q test/test_assembler.py test/test_runtime_units.py test/test_runtime_driver.py
uv run --locked make -B -C test
```

The default regression includes the five baseline tests plus three UART and
one SPI probe tests, and the [JTAG TAP test](wave_b_results.md), for ten total.
Select an individual module with
`COCOTB_TEST_MODULES=test_uart_probe` or `COCOTB_TEST_MODULES=test_spi_probe`.
The test Makefile is also used by CI, so these probes are part of its default
RTL regression. Run serially in the same build directory; use separate
SIM_BUILD and results paths if running independent simulators concurrently.

The [machine-readable record](protocol_probe_results.json) contains actual
commands, test names, outcomes and source hashes. A passing mapped baseline
does not mean the new firmware has mapped test coverage. RTL physical-source
hashes still match the prior runtime flow; test/firmware hashes have changed.
No fresh synthesis or PnR is needed for these firmware-only probes, and none
was performed. Existing fanout, CDC, pad, power and physical-signoff gaps
remain unchanged.

## Next experiments

1. The [I2C register TX/RX candidate](i2c_capacity_study.md) and independent
   open-drain peer now exercise repeated START, ACK/NACK, stretching and
   bounded recovery on an explicit 256-word model. Resolve its 249-word
   capacity blocker before claiming this behavior on the actual 128-word ASIC.
2. [JTAG, SWD and PS/2 initial experiments](wave_b_results.md) now have independent
   peers. JTAG runs on production RTL; SWD/PS2 have reproduced candidate capacity
   failures and explicit larger-model evidence. Production capacity stays open.
3. [Ethernet minimum-frame TX/RX](ethernet_capacity_study.md) now has larger-model
   evidence and an actual capacity failure. [CAN RX/live CRC/ACK](can_receive_study.md)
   now passes on a larger model; [CAN TX](can_transmit_study.md) passes separately,
   while combined-image capacity, remaining CAN node behavior and USB remain open.
   Preserve failing cases and distinguish resource limits from incomplete firmware.
4. Complete the full UART/SPI acceptance contracts alongside broad coverage;
   these probes do not close their remaining milestones.
