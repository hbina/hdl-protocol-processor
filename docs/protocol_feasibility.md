# CAN, USB and Ethernet feasibility

Study date: 2026-11-08. These are architecture decisions for future work, not
implemented protocols or component/board qualification. No traffic has been sent
on a physical CAN, USB or Ethernet link.

## Constraints from the implemented processor

The engine has eight logical input/output pins, 64 scratch bits, a single 16-bit
loop counter and at most 256 32-bit instructions. It has no packet RAM, FIFO,
DMA, interrupt controller, edge timestamping or autonomous clock-recovery engine.
WAIT stalls instruction execution and sampling. SAMPLE_AND_SET can sample one
bit while changing outputs; it does not simultaneously perform framing, CRC,
buffering or synchronization. See the [implemented contract](protocol_processor.md).

For comparison, these are arithmetic budgets at an **assumed** 100 MHz execution
clock, not a demonstrated achievable frequency:

| Candidate link | Link interval | Processor clocks per interval |
|---|---|---|
| Classical CAN at 1 Mbit/s | One serial bit | 100 |
| USB full speed at 12 Mbit/s | One serial bit | 8.33 |
| 100 Mbit/s RMII alternative | One two-bit symbol at 50 MHz | 2 |

These budgets exclude synchronization, peripheral propagation and setup/hold
margins. Even a budget greater than one is insufficient evidence for an engine
that must perform several state updates per bit. Generic synthesis measures
logic cells/depth but supplies no frequency for these calculations.

## CAN: select Classical CAN with an external controller

Initial role: a single application node using ordinary 11-bit identifiers, up to
eight data bytes, with 1 Mbit/s as a design study point. CAN FD and extended
identifiers are outside the first milestone. CAN needs arbitration while
monitoring the bus, bit synchronization, stuffing, CRC and error handling;
Microchip documents these [core CAN mechanisms](https://developerhelp.microchip.com/xwiki/bin/view/applications/can/overview/mechanisms/).

Decision: use a dedicated CAN controller plus an external CAN transceiver rather
than promise direct bit-level CAN in this engine. Microchip's
[MCP2515](https://www.microchip.com/en-us/product/MCP2515) illustrates the SPI
controller boundary; electrical transceiver/voltage/termination selection remains
a target integration task. The programmable processor would configure the
controller and move bounded messages. The controller owns bus timing and errors.

Candidate electrical interface: [MCP2562FD](https://www.microchip.com/en-us/product/MCP2562FD)
with its VIO matched to the controller, used here for Classical CAN rather than
FD traffic. Plan a 16 MHz controller oscillator and an 8.33 MHz SPI study point
(50 MHz engine, half-period 3); these are integration assumptions to validate,
not measured external-link rates. The [MCP2515 data sheet](https://ww1.microchip.com/downloads/en/DeviceDoc/MCP2515-Family-Data-Sheet-DS20001801K.pdf)
provides three TX and two RX message buffers. A future host-side 256-byte queue
allocation (eight 16-byte entries per direction) would decouple bounded bursts;
neither that RAM nor a latency guarantee exists in the current core.

Current SPI is insufficient for this interface: it transfers one byte and
deasserts select afterward. A peripheral driver needs multi-byte command sequences
with select held, register operations, status/error handling and message buffers.
The 64-bit scratch bank cannot hold a complete eight-byte payload plus software
CRC/status work. A streaming or RAM-backed data interface is required before a
useful sustained-message API. No controller driver is implemented by this study.

Acceptance gate: independent SPI peripheral model, full message read/write,
controller-status tests, bus-off/error recovery responsibilities, queue/backpressure
limits, and transceiver/board tests at a selected bit rate. Direct-CAN work would
instead require a separate autonomous bit-timing and protocol engine.

## USB: select a full-speed device with a dedicated packet engine

Initial role: USB 2.0 full-speed device with endpoint zero/control and one small
application endpoint. Host, hub, high speed and Type-C/PD policy are excluded.
TI's [TUSB1105](https://www.ti.com/product/TUSB1105) is an example external
full-/low-speed electrical transceiver, not a USB device controller. Packet
identification, CRC, NRZI, stuffing and endpoint buffers are separate functions;
NXP's [USB device-controller description](https://www.nxp.jp/docs/en/application-note/AN3565.pdf)
shows this separation. The authoritative specification entry is
[USB-IF USB 2.0](https://www.usb.org/document-library/usb-20-specification).

Decision: the processor acts as a control engine behind a dedicated USB serial
interface/packet engine and endpoint FIFOs. A PHY alone does not make this engine
USB-capable. The small instruction image and scratch bank provide neither a
proven full-speed receive schedule nor endpoint storage and packet turnaround.
The eight-clocks-per-bit comparison is only a reason to demand an explicit
schedule, not a proof that a future specialized implementation is impossible.

The future interface needs endpoint RAM, host-visible request/completion/status,
bounded FIFO backpressure, and an explicit clock-domain crossing. The engine
would service descriptors/control requests at the transaction level; dedicated
logic would handle packet deadlines. Choose buffer sizes from maximum endpoint
packet sizes and burst/backpressure requirements, rather than the scratch bank.
For the first design study, budget a separate 48 MHz full-speed packet-engine
domain, 512 bytes of endpoint SRAM (384 bytes for double-buffered 64-byte EP0
and application RX/TX paths, with 128 bytes for bookkeeping/control storage),
and a FIFO/register crossing to the 50 MHz processor. These are proposed budgets
requiring a packet-engine implementation and validation, not added core features.

Acceptance gate: packet/CRC/stuffing tests, endpoint-zero enumeration and request
handling, reset/suspend/resume, independent host traffic, malformed packets,
buffer overflow/underflow and PHY timing. No USB packet or enumeration engine is
implemented by the existing UART/SPI examples.

## Ethernet: select a buffered 10BASE-T endpoint offload

Initial role: bounded raw layer-two frame transmission/reception through an
external MAC/PHY controller. IP/TCP applications, PHY implementation and a direct
100 Mbit/s MAC are separate work. Microchip's
[ENC28J60](https://www.microchip.com/en-us/product/enc28j60) illustrates a
10BASE-T MAC/PHY with 8 KiB buffer RAM and an SPI control/data interface.

Decision: use buffered MAC/PHY offload for the first endpoint. A direct RMII
alternative such as [LAN8720A](https://ww1.microchip.com/downloads/en/DeviceDoc/00002165B.pdf)
requires a MAC, two-bit data paths and a 50 MHz reference domain; a PHY is not a
MAC. The assumed two-processor-clock budget per RMII symbol leaves no demonstrated
schedule for frame state, CRC and buffering. It also lacks CDC and packet RAM.

As with CAN, held-select multi-byte SPI and streaming/buffer access must precede
an external-controller driver. The controller's own RAM absorbs link bursts;
software must still bound service latency and prevent FIFO overrun. Its advertised
line rate does not imply the processor can sustain that rate over its SPI API.
Use the controller's specified 25 MHz oscillator boundary and study SPI at
8.33 MHz. Plan 6 KiB of its buffer for RX and 2 KiB for TX, budgeting three large
RX frames plus headroom and one TX frame. The SPI bit rate is below the 10 Mbit/s
wire rate, so this selected path explicitly targets bounded bursts, not sustained
line-rate reception. Service latency and overflow handling need measurement.

Acceptance gate: independent controller/buffer model, whole-frame read/write,
length/FCS ownership, receive overflow, transmit completion/errors, reset and
link-state changes; then real PHY/magnetics/board tests. A later direct RMII MAC
requires dedicated framing/CRC/FIFO logic with a domain-specific timing analysis.

## Result and next decision

The study is complete at the architecture level: all three links need buffering
and dedicated link logic or external controllers. They should not be advertised
as additional bit-banging programs on the current engine. The next implementation
gate is a data-stream/RAM interface and held-select SPI, followed by a selected
controller/packet-engine integration. The block study now selects SKY130 HD at
50 MHz; external-controller interfaces still need appropriate IO/level shifting,
clock/synchronization budgets and board validation. The candidate components and
RAM allocations above remain future integration choices, not qualified hardware.
