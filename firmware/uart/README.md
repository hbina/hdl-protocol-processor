# Standalone UART firmware

Three independent programs implement 8N1 using the existing generic processor.
There are no UART RTL changes, predecessor imports, patch chains, or host queues.
The generated `.asm` files are the default 50 MHz / 1 Mbaud listings.

| Program | Default words | Purpose |
|---|---:|---|
| transmit.py / transmit.asm | 38 | Initialize a RAM payload and repeat it with back-to-back frames |
| receive.py / receive.asm | 70 | Continuously receive into a bounded RAM buffer; drop new bytes when full |
| echo.py / echo.asm | 69 | Receive one byte, store it in RAM, transmit that stored byte, then rearm |

Build or inspect a program from the repository root:

```sh
uv run --locked python -m firmware.uart.echo --baud 1000000 -o /tmp/uart_echo.asm
uv run --locked python -m tools.assembler /tmp/uart_echo.asm --disassemble
uv run --locked python -m firmware.uart.transmit --payload-hex '0011a5ff55' --baud 115200 -o /tmp/uart_tx.asm
uv run --locked python -m firmware.uart.receive --capacity 128 --baud 9600 -o /tmp/uart_rx.asm
```

Direct-file invocation, for example `uv run --locked python firmware/uart/echo.py`,
also works. Each generator constructs its own complete typed `Program` with instruction
constructors and `Label` objects, then links it directly. Text assembly is an output
listing only; no checked-in artifact or text parser is needed for generation. Upload the generated words using the normal
[configuration interface](../../docs/pin_processor.md); keep external RX idle high
while loading. Wait for READY before the first received frame.

## Physical pins and observable state

| Physical pin | Meaning |
|---|---|
| uio[0] | TX, idle high in TX/echo; released by RX-only firmware |
| uio[1] | RX input, idle high; unused by TX-only firmware |
| uio[2] | READY in RX/echo: high while waiting for a new start |
| uio[3] | VALID in RX/echo: high after accepting a byte; cleared at the next start |
| uio[4] | Sticky rejected-start flag |
| uio[5] | Sticky framing-error/break flag |
| uio[6] | Sticky RX-buffer overflow flag; RX-only program |
| uio[7] | RX buffer full; RX-only program |
| uo[7:0] | Last accepted RX byte, retained across rejected/dropped frames |

All status outputs are firmware-controlled GPIO. They are not a request/response
transport or a claim of UART RTS/CTS support. Error flags and counters clear on
firmware restart/reload. The three programs must be loaded separately.
TX-only supports `--tx-pin 0..7`; RX/echo use the fixed mapping above.

## RAM and traffic contracts

**Repeating TX:** `--payload-hex` supplies arbitrary bytes at build time. Firmware
initializes RAM[0..N-1], then LOADs each byte for transmission and wraps the pointer.
It does not reset or reload between bytes or passes. N is 1..64, subject to the
256-word program limit. At the default baud the largest payload uses 218 words.
Slow baud rates need extra WAIT instructions: 9,600 baud allows at most 50 payload
bytes (256 words). Oversized generated images fail rather than truncate.

**Continuous RX:** `--capacity` is 1..240, default 128. Accepted bytes fill
RAM[0..capacity-1] in order. Once full, each further valid frame is decoded and
dropped; stored payload and the last accepted output byte are preserved. FULL
stays high, OVERFLOW becomes sticky, and RAM[243] counts drops modulo 256.
RAM[241] counts rejected starts and RAM[242] counts framing errors, also modulo
256. These counters are initialized by firmware. RAM outside initialized/written
locations is unspecified. There is no buffer consumer or reclamation operation;
restart/reload is required to empty a full buffer. READY reflects listening state,
not free capacity; use FULL to determine whether additional bytes can be stored.
After initial arming, valid RX frames can arrive back-to-back with one stop bit.

**Sequential echo:** RAM[0] is a one-byte staging location. The accepted byte is
stored, then LOADed by the transmitter. RAM[241]/[242] count rejected starts and
framing errors. There is no accumulation buffer or simultaneous TX/RX. The sender
must wait for READY, keep RX high for one more bit, send exactly one frame, and
wait for the next READY before sending again. READY stays low during receive,
transmit, and rearming. Traffic sent while busy is unsupported: it may be lost or
misframed, and there is no promise to count every such loss. A tested all-zero
busy frame is ignored and subsequent valid traffic recovers after idle.

## Timing and error behavior

`--clock-hz` (default 50,000,000) must match the actual execution clock.
Keep the clock stable and ena high during traffic; pausing the processor mid-frame
does not pause the external UART peer.
`--baud` selects a constant integer bit period, rounded to the nearest clock.
There must be at least 50 clocks per bit, at most 1% baud-rounding error, and the
whole program must fit in 256 words. These are generation-time options, not
runtime registers. Parity, other data widths, and extra stop bits are deferred.

| Requested baud at 50 MHz | Clocks/bit | Actual baud | TX / RX / echo words, default payload/capacity |
|---|---:|---:|---|
| 1,000,000 | 50 | 1,000,000 | 38 / 70 / 69 |
| 250,000 | 200 | 250,000 | 38 / 70 / 69 |
| 115,200 | 434 | approximately 115,207.37 | 42 / 72 / 74 |
| 9,600 | 5,208 | approximately 9,600.61 | 118 / 144 / 203 |

RX waits for a synchronized low, checks the start at half a nominal bit, samples
eight LSB-first data bits one nominal bit apart, then checks the stop midpoint.
A high mid-start sample rejects the candidate; a low stop sample reports a framing
error without publishing/storing the byte. Sustained low produces one framing
error and waits for high rather than repeatedly filling the buffer with zeros.
Boot, error recovery and post-echo rearming require a sampled high interval of at
least one nominal bit. Qualification samples are spaced three clocks apart
(four at chunk boundaries for long intervals); this is not a general glitch filter.
Good RX-only frames bypass requalification so one-stop-bit traffic stays continuous.

Input synchronizer latency is in addition to firmware sampling. After malformed
traffic allow a high idle interval and wait for READY before resuming. The tested
RX tolerance is peer bit duration 98%, 100%, or 102% of the generated bit period;
this is selected simulation coverage, not full UART interoperability signoff.

## Verification

```sh
uv run --locked pytest
uv run --locked pyright
uv run --locked make -B -C test
uv run --locked make -B -C test SIM=verilator
# UART groups only:
uv run --locked make -B -C test COCOTB_TEST_MODULES=pin_uart
```

The independent serial peer checks all 256 TX and echo values, repeated RAM buffer
passes, exact TX transition spacing, 20 start-phase offsets spanning a 20 ns core period,
back-to-back RX at four baud settings and three peer bit durations, capacity/overflow
boundaries, false starts, invalid stops, sustained break, error recovery, and the
sequential echo READY contract. RAM is inspected only in RTL to verify storage and
counters; external pin checks also apply to mapped hardware once available.
The original [UART verification record](../../docs/uart_verification.json) records
behavior before the typed-builder conversion. The current
[typed-construction record](../../docs/typed_instruction_verification.json) includes
the 47 exact pre/post profile comparisons and fresh suite results. No board, new routed timing,
or mapped protocol result is claimed.
