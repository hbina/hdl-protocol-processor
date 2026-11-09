# Protocol example interfaces

## UART transmit

The 8N1 frame convention follows Microchip's
[USART asynchronous waveform](https://ww1.microchip.com/downloads/en/DeviceDoc/usart.pdf).

`protocols::uart::transmit(bytes, pin, period)` builds a checked program for UART
8N1 transmission. Pin indices are 0..7. Period is an integer in 1..=65536 processor
clocks; no frequency conversion or silent rounding occurs. Baud is execution
clock frequency divided by period; assess baud error for the selected target.

The program emits one idle-high bit interval, then start-low, eight data bits
LSB first, and stop-high for each byte, with no extra inter-byte interval. HALT
leaves the line high. Other output pins retain their values. Empty payloads emit
idle followed by HALT. Reset still clears pins to zero; the first instruction
establishes idle high and enables the selected output. Reset releases all pads;
an external idle-high requirement during reset needs pull-up/top integration.

An interval of N clocks uses SET_PINS plus WAIT(N-1), with WAIT omitted for N=1.
The first SET_PINS is replaced by CONFIGURE_PINS to enable the output atomically.
WAIT(0) is never emitted. For B bytes, image size is `2*(1+10*B)+1` at N>1 and
`1+10*B+1` at N=1. Maximum payload is 12 or 25 bytes respectively; larger images
are rejected before allocation of an instruction image. Period 65536 uses the
maximum WAIT(65535).

Host code can pass UTF-8 text as bytes. The Rust builder accepts
arbitrary bytes. The transmit builder has no flow control, parity variants,
buffering or board validation. Receive is a separate builder described below.

## Input polling

`poll::input_high(pin, attempts, gap)` polls a synchronized input, reporting success
in scratch bit 62 or timeout in bit 63. Attempts and gap are nonzero 16-bit values.
Each unsuccessful iteration consumes `gap+3` clocks (capture, branch, WAIT(gap),
decrement/branch). First capture occurs at zero-based edge 1 after LOAD_COUNT.
Timeout takes `1 + attempts*(gap+3) + 2` edges from zero state. A successful sample
halts three edges after capture. Start each invocation with reset state. Tests
move input transitions across sample boundaries.

## SPI controller

`spi::transfer(byte, config)` performs one eight-bit full-duplex transfer. It
supports modes 0..3, MSB-first or LSB-first, distinct clock/MOSI/MISO/select pins,
and half-periods 2..=65536 clocks. Received data is exposed in scratch bits 32..39.
Other scratch bits and unrelated output pins are preserved. Initial configuration
enables clock/MOSI/select and releases MISO. CPOL and CPHA follow
Microchip's [SPI transfer modes](https://onlinedocs.microchip.com/oxy/GUID-A299F4E7-F38C-4DF5-96C0-A87B9F519156-en-US-4/GUID-8A5B8750-B99E-4176-834E-E44E98F4A098.html):
mode bit 1 selects idle polarity, bit 0 selects leading/trailing sampling phase.

At edge zero the builder establishes idle clock and inactive select. Edge 1
asserts select; first leading edge is at `1+half_period`. Eight leading and eight
trailing edges are separated by the half-period. Select deasserts at
`1+17*half_period`; HALT follows one edge later. Phase zero prepares the first
MOSI bit when selecting and later bits on trailing edges. Phase one prepares data
on leading edges. Final clock is idle and select high.

SAMPLE_BIT reads MISO one processor clock after the selected SPI sampling edge,
while SCK is held at that phase. The peer's data and external synchronization
latency must meet that sampling window. The two-clock minimum is a functional
lower bound, not a board-level rate guarantee. The independent test peer changes
MISO at setup edges and checks MOSI at sampling edges. No multi-byte transfer,
slave role or peripheral-specific timings are claimed. Half-period 65536 is
accepted but full waveform regressions use 2/3/8.

## UART receive

`uart::receive(pin, period, attempts)` receives one 8N1 frame from synchronized
inputs. Period must be even and in 8..=65536, attempts 1..=65535. It polls for a
low start every three clocks, checks start at half a period from detection, then
samples eight data bits and stop one period apart. Sampling phase includes up to
two clocks of polling latency; external synchronizer latency and baud error need
their own integration budget. This is not an oversampling or baud-recovery engine.

Scratch bits 32..39 contain data, 62 success, 63 protocol error, 61 start timeout,
and 60 false start. A low stop sets error without either subcode. Flags assume
zero initial state; reset before an independent invocation. Timeouts bound start
polling, not the duration of an already detected frame. UART errors halt normally;
they do not set processor fault.

Tests cover all byte values and every polling phase at period 16, selected bytes
at periods 8/32, low stop, one-clock false start, and no-start timeout. They also
verify first-frame decoding when a second start immediately follows its stop.
`receive_frames(pin, period, attempts, count)` receives 1..=6 frames in one run,
including immediately adjacent frames, storing bytes in scratch bits 8..55.
It shares the single-frame timing/status contract, preserves each earlier byte,
and halts on the first error. Attempts bound start polling independently for each
frame. Status bits must be clear on entry. Batches use at most 174 words; they are
not a FIFO or unbounded continuous receiver. Another 780 independent scenarios
check complete two-/six-frame captures and a later bad stop, including all byte
values and polling phases at period 8. Maximum
period acceptance is checked without simulating a complete maximum-period frame.

## I²C controller

The byte/acknowledge and START/STOP conventions follow NXP's
[UM10204 revision 7](https://www.nxp.com/docs/en/user-guide/UM10204.pdf).
`i2c::transaction(address, transfer, config)` supports one-byte Write/Read
transactions at ordinary seven-bit addresses 0x08..=0x77, with distinct SCL/SDA
pins, nonzero hold clocks and nonzero SCL sampling attempts. Repeated START,
multi-byte transfers, arbitration, bus clearing and reserved-address modes remain
unsupported. This is a single-controller example.

CONFIGURE_PINS always sets selected values to zero: enable means drive low,
disable means release. The program releases both lines, checks idle, emits START,
address plus direction, target ACK, one byte, and its acknowledge cycle. Reads
finish with controller NACK. Both successful and NACK paths emit STOP. Busy-bus
and clock-timeout paths release both lines without promising STOP while a peer
holds SCL low. Every halt path releases both owned outputs.

Scratch bits 32..39 contain read data, 62 success, 63 error, 61 NACK, 60 busy and
59 SCL timeout. Status bits 59..63 are cleared on entry. Bits 0/1 are temporaries.
Other bits are preserved. Both address and write-data NACK are detected. Every
SCL release, including STOP, polls resolved SCL before proceeding. This bounds
clock stretching by a caller-selected attempt count rather than a protocol-wide
time limit. At most `3*attempts-2` modeled stretch clocks can precede a successful
last sample; the following clock crosses the tested timeout boundary.

`hold` is an additional minimum hold, not a requested bus period: instruction,
sampling and branch cycles also consume clocks. Select physical rates and input
latency against a target/peripheral timing budget. Logical tests use zero-delay
pull-ups and no synchronizer latency; they do not establish I²C electrical or
speed-grade conformance.

## JTAG controller

`jtag::scan(kind, value, width, config)` resets the TAP with five TMS-high clocks,
enters Run-Test/Idle, selects IR or DR, shifts 1..32 bits LSB first, updates and
returns to Idle with TCK low. Pins are distinct TCK/TMS/TDI/TDO; outputs are
enabled and TDO is released. `hold` is nonzero. Values exceeding the selected
width are rejected. Captured TDO is in scratch bits 0..width-1; other bits hold.

The sequence follows Microchip's [TAP controller description](https://onlinedocs.microchip.com/oxy/GUID-74F8229E-4C43-4FA0-BE7D-1AA303C6F8A4-en-US-6/GUID-4A877CE6-1E9A-4679-BE1B-11E7C5C25C31.html).
TMS/TDI are stable during high TCK; sampling TDO one processor edge after rising
TCK assumes the target holds it until falling TCK. A 32-bit IR scan occupies 211
words. `sequence(&[Scan], config)` resets once, then preserves TAP state across
IR/DR scans. Each Scan assigns a nonoverlapping capture range in the 64-bit bank.
A four-bit IR plus 32-bit DR sequence occupies 251 words; tests prove the selected
instruction survives into DR capture and both results remain available. Larger
sequences reject capacity/range errors. Adjacent pulses share their falling/setup
edge, with one final falling edge before HALT. No device instruction set, chain
discovery, TRST, debug transport or
board timing validation is provided.

## PS/2 device transmit

`ps2::device_transmit(byte, config)` sends start, eight LSB-first data bits, odd
parity and stop using open-drain clock/data controls. The device generates the
clock; the host model captures on falling edges. Framing and inhibit behavior
follow Infineon's [PS/2 device description](https://www.infineon.com/dgdl/Infineon-PS2D_001-13681-Software%2BModule%2BDatasheets-v01_02-EN.pdf?fileId=8ac78c8c7d0d8da4017d0fab8b401c89)
and Microchip's [PS/2 interface description](https://ww1.microchip.com/downloads/en/DeviceDoc/ECE1117-Data-Sheet-DS00001860E.pdf).

Config selects distinct pins, additional high/low `hold`, `idle_hold`, and bounded
initial clock-high sampling attempts, all nonzero. The initial inhibit can clear
within that budget. Before transmitting, both lines are sampled high around the
idle hold. Inhibit detected during a frame aborts, releases both outputs and
reports status; it does not resume a partial frame. Host request-to-send detected
before transmission likewise returns control to the caller. Success releases both
outputs after the stop bit. Data changes while clock is high before its sample.

Scratch 62 is success, 63 error, 61 mid-frame/qualification inhibit, 60 pending
host request and 59 initial inhibit timeout; these flags are cleared on entry.
Bits 0/1 are temporaries. Host-command reception and automatic retransmission are
not implemented. Idle qualification samples endpoints, so short intervening
glitches are not detected. The integrator must supply a stable qualified idle
interval, select clocks meeting physical idle/bit timing, and account for input
synchronization. The test clock counts do not establish a keyboard/mouse-compatible
bit rate or electrical interface.

## SWD host transfer layer

`swd::transaction(ap, address, transfer, config)` performs one raw 32-bit DP/AP
read or write, with register addresses 0/4/8/12. It follows Arm's
[CMSIS-DAP transfer sequence](https://github.com/ARM-software/CMSIS-DAP/blob/main/Firmware/Source/SW_DP.c)
and [SWD configuration contract](https://arm-software.github.io/CMSIS_5/DAP/html/group__DAP__SWD__Configure.html):
one turnaround clock, with no data phase on WAIT/FAULT. The target must already
be in SWD mode with matching configuration. AP posted-read management, sticky
overrun mode, multi-drop selection and connection/authentication are not provided.

The builder emits request start/AP/RnW/address/even-parity/stop/park, releases
SWDIO for turnaround and three ACK bits, then transfers 32 data bits plus even
parity. WAIT retries the identical request up to `attempts` total tries, with an
optional processor-clock `retry_gap`. FAULT terminates. Invalid ACK clocks through
a possible 33-bit data phase while released, then hands back ownership and fails.
Return turnaround finishes before host output enable; tests reject ownership
overlap even if both values would agree. The engine ends with a low-data idle
clock, then SWCLK low/SWDIO driven high. Hold/attempt counts are nonzero; pins are
distinct. Hold is an additional clock-phase delay, not a guaranteed physical rate.

Read data is scratch bits 32..63. Status bits 8..13 are cleared on entry and mean,
respectively: success, error, WAIT exhaustion, FAULT, parity error, invalid ACK.
Bits 0..5 are ACK/parity temporaries. A write transmits the caller's 32-bit value.
Wrong read parity retains the observed data but reports error. The read image
uses 241 words with retry_gap=0, 242 otherwise, independent of runtime attempt
count. Generic SAMPLE_AND_SET and PARITY_WORD instructions keep it within capacity.

`swd::line_reset(config)` emits 56 high-data clocks and two low-data idle clocks,
then parks high. It does not perform JTAG-to-SWD or dormant/multi-drop switching.
The 549 independent wire-model cases cover all request fields across data cases,
read/write, all ACK values, retries/exhaustion, parity errors, alternate pins and
holds. Logical pad tests exercise both high and low target drive with explicit
turnaround ownership; target timing/board behavior remains unverified.

## CAN, USB and Ethernet study

The [feasibility study](protocol_feasibility.md) selects initial roles and
buffer/controller boundaries. CAN, USB and Ethernet protocols/drivers remain
unimplemented. A study is not link-level verification. See the
[implementation plan](protocol_processor_plan.md) for remaining gates.
