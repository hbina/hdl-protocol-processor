# Bidirectional protocol exploration

Plan established: 2026-10-24. This is the implementation and acceptance plan;
it does not claim that the planned capabilities already exist. Current results
remain in [the README](../README.md) and [runtime evidence](runtime_results.json).
Organizer guidance is archived in [the competition email](competition_email.md).

The [2026-10-25 acceptance audit](protocol_acceptance_audit.md) checks current
source/result integrity and reproduces all seventeen production capacity failures.
Initial experiments cover all nine protocols; the original acceptance gates
remain open where features/tests are missing. UART has progressed through the
named runtime tests and software-clock deadline acceptance on a251-word model
candidate. JTAG invalid-length handling now passes on a198-word/four-register
candidate. The [701-word CAN follow-up](can_ack_recovery_study.md) now passes
missing-ACK active flags and at most three attempts in generic firmware, with
three independent-peer groups. The [811-word winner follow-up](can_winner_study.md)
now receives/ACKs winners and retries retained data with three more groups
passing. The [819-word phase follow-up](can_resync_study.md) adds bounded RX
falling-edge correction; three groups pass and the fixed-clock failure remains
reproducible. The [1,020-word fault-state image](can_fault_state_study.md) now
adds persistent counters, selected active/passive TX flags and bus-off/recovery
using existing generic calls. Five groups pass with passive-flag/inlining
failures preserved. The [1,021-word RX-flag follow-up](can_receive_flags_study.md)
now adds timed CRC/stuff/selected form flags and compacts a1,069-word candidate
without ISA/RTL changes; five groups pass. The
[1,023-word post-flag follow-up](can_postflag_study.md) adds receiver first-bit+8
and prolonged-dominant+8 counting with five groups passing and no new ISA/RTL.
One model word remains; flag bit-error accounting and full timing remain open.
The [active-flag fault study](can_flag_bit_study.md) now reproduces two counter
failures and one passing passive control; its1,076-word integration fails model
capacity and has no behavioral proof. The separate
[1,024-word compact image](can_flag_compact_study.md) recovers52 words and now
passes five fault/restart groups, five earlier post-flag groups and two selected
RX groups. No new ISA/RTL/RAM is added; zero model words remain. The
[RX-tail investigation](can_tail_study.md) now reproduces three wire gaps and
one passing ordinary-frame control. Its1,067-word draft fails model capacity;
behavioral proof and TX tail/overload-fault handling remain open.

Progress on 2026-10-24: [UART and SPI exploration probes](protocol_probe_results.md)
now pass arbitrary runtime-payload TX/RX tests on the unchanged RTL. These
valid-request probes do not yet fulfill all acceptance requirements below;
UART's poll-count timeout differs from the planned clock deadline. The full
nine-protocol goal remains open. The [I2C capacity study](i2c_capacity_study.md)
now preserves a 249-word TX/RX candidate and its 128-word assembly failure;
behavior is tested separately on an explicit 256-word model, not production RTL.
Wave B now has [JTAG, SWD and PS/2 experiments](wave_b_results.md): JTAG fits
the actual 128-word core; SWD/PS2 candidates reproduce capacity failures and
are tested only on explicit 256-word models. On 2026-10-25,
[Ethernet minimum-frame TX/RX](ethernet_capacity_study.md) passes only on an
explicit 512-word generic-address model; its 280-word image exceeds production
capacity. [CAN RX with live CRC and ACK](can_receive_study.md) now passes four
tests on that explicit larger model, but its 335-word receive image exceeds
actual capacity. [CAN TX](can_transmit_study.md) now passes four tests separately
on that model, including CRC/stuffing/ACK, bit monitoring and arbitration-loss
release; its 318-word image also exceeds actual capacity. The combined 622-word
source exceeds even 512 and is not simulated. Combined TX/RX, winner reception,
retries/resynchronization/error frames and USB remain open; no production
capacity change is selected.

[USB packet reception](usb_receive_study.md) now has two generic-ISA candidates
(400/391 words) with five packet tests each on explicit 512-word models. Both
preserve actual capacity failures and a failing USB ACK-turnaround requirement;
the firmware optimization reduces latency but does not meet the deadline.
USB enumeration and control transfers remain unimplemented. All nine protocols
have initial experiments; their original acceptance gates below are unchanged.

The [generic frontier experiment](generic_frontier_study.md) now tests a
1024×18/eight-register core in isolation, motivated by CAN capacity and USB
register pressure. Combined CAN alternates TX/RX without reload; three model
tests and the ten legacy tests pass. Unmapped core synthesis quantifies a
large storage cost. Production RTL/encoding/storage and USB response timing
remain unresolved; this is not a supported ASIC configuration.

[Live USB](usb_live_study.md) now meets the packet-response window using that
register/storage experiment plus generic leaf calls: 947 words versus 1,221
when its CRC routine is inlined. Packet tests and legacy regression pass, but
tokens, enumeration, control transfers and production physical fit remain open.

The [addressed USB follow-up](usb_out_study.md) now adds firmware token CRC5
and OUT/SETUP gating at minimum token-to-data spacing. Generic carry shifts
reduce the receiver to 310 words and the addressed image uses 403 words.
IN payloads, reset, endpoint state, enumeration and production physical fit
remain open; these model results do not close the full USB acceptance gate.

The [629-word bidirectional image](usb_in_study.md) adds firmware IN DATA encoding,
host ACK/retry and alternating IN/OUT requests without reload. All six test
groups pass on the same carry model. A host preparation interval is still
required; reset, autonomous endpoint state and enumeration remain open.

The [live TX/control follow-up](usb_control_study.md) now computes transmit CRC
and encoding live (648 words), and a 776-word image autonomously handles a vendor
control write/status/read/status at address0/EP0. Six live packet tests and three
control tests pass, including short gaps and retry/recovery checks. Reset,
standard requests, address changes and enumeration still gate full USB support.

The [921-word reset/address image](usb_address_study.md) adds qualified bus reset,
deferred SET_ADDRESS and vendor control readback at assigned addresses. Six model
groups and two new units pass. Descriptors/configuration, multi-packet control
state and enumeration remain open; 103 words remain in the isolated model.

The [1,012-word enumeration image](usb_enumeration_study.md) now executes a
selected reset/descriptor/address/configuration sequence and arbitrary vendor
control readback with an independent host. Descriptor chunks advance PID/pointer
only after ACK, with the slower short-gap failure preserved. Ten model groups
and two new units pass; general USB request coverage, jitter/board proof and
production fit remain unresolved. Twelve words remain in the model.

## Goal and architectural invariant

Attempt basic, valid transmit and receive operation for UART, SPI, I2C, JTAG,
SWD, PS/2, classical CAN, low-speed USB, and 10 Mbit Ethernet. Learn their
requirements by implementing exchanges, measure where the architecture fails,
then improve generic facilities or make explicit scope cuts.

**Every protocol is described entirely by firmware using the generic ISA.**
No protocol-specific RTL engines, opcodes, modes, CRC units, framing parsers,
arbitration state machines, or retry controllers are allowed. Encoding,
decoding, CRC/parity, transaction state, and recovery execute as instructions.
An external electrical transceiver or PHY is permitted only at an explicitly
documented boundary. It must not silently supply a protocol controller/MAC.

Generic additions may provide storage, bit operations, pin sampling/driving,
edge capture, timed execution, buffering, or programmable execution contexts.
Their semantics and hardware interfaces must make no reference to a protocol.
An extension proposal must explain its instruction-visible behavior, motivating
failing test, cycle/area tradeoff, and a second plausible use. Demonstrating that
second use is a follow-up verification goal, not grounds to invent another engine.

Exploration succeeds for each protocol with either a passing bidirectional
demonstration or a reproducible blocker. A blocker is evidence about a concrete
attempt, not a replacement for trying the protocol. Preserve its source,
command, expected/actual result, limiting resource, and candidate generic fix.
Do not label an unimplemented test or a rough estimate a reproduced blocker.

## Shared acceptance contract

- The host supplies arbitrary payloads or transaction parameters at runtime.
  Host preprocessing must not replace firmware framing, CRC, bit stuffing, or
  decisions based on received data. Diagnostic precomputed waveforms are useful
  stepping stones, not passing bidirectional demonstrations.
- Firmware returns received data and a terminal status through the runtime ABI.
  Each firmware image documents operations, argument layout, metadata, counts,
  error codes, and a finite completion/recovery bound.
- Repeat successful and failed requests without resetting/reloading the ASIC.
  Different protocols may use different firmware images. Simultaneous protocols,
  multiple roles, continuous unsolicited reception, and unlimited streams are
  outside the first milestone unless needed for a selected valid exchange.
- Use an independent peer model at the public pins, with its own protocol
  state and expected data. Do not derive the expected waveform from the DUT
  instruction trace. Include varying data, boundaries, and malformed traffic.
- Document rates, payload bounds, pin assignment, external hardware, and
  limitations. Validate synchronized input latency and phase offsets.
- Keep three evidence levels separate: functional RTL simulation; mapped
  functional simulation plus extracted physical timing; FPGA/board or silicon
  interoperability. None implies a later level. Historical physical evidence
  remains attributable to its original source hashes.

## Experiments and order

Targets below are proposed experiment rates, not achieved results. Begin with
functional models and one role. Increase rates/configurability after basic TX/RX.

| Wave | Protocol / role | First rate | Runtime transaction / payload scope | External boundary |
|---|---|---:|---|---|
| A1 | UART, TX and RX | 115200 baud, 8N1 | Send 0..64 bytes, then receive 0..64 bytes in a bounded response window | Logic-level UART peer; level shifter if needed; no UART controller |
| A2 | SPI, controller mode 0 | 100 kHz SCLK | One CS-low exchange, 1..64 arbitrary bytes each way | SPI peripheral with compatible voltage |
| A3 | I2C, 7-bit controller | 100 kHz SCL | Register write followed by register read; <=64 input and output entries per request | Pull-ups and target; firmware controls open-drain drive/release |
| B1 | JTAG, controller | 100 kHz TCK | TAP reset, IR selection, DR shift with arbitrary input/output bits | Single TAP target; optional voltage translation |
| B2 | SWD, host / DP access | 100 kHz SWCLK | Read/write 32-bit DP registers, including a writable test register | SWD target; pull-up/voltage translation as required |
| B3 | PS/2, host | Device model 12.5 kHz; test 10..16.7 kHz | Send a command, observe link ACK, receive device response and device-originated bytes | Open-drain clock/data, pull-ups and 5 V translation where required |
| C1 | Classical CAN, standard data frames | 125 kbit/s | TX/RX 11-bit ID and 0..8 payload bytes with a participating peer | CAN transceiver, terminated bus; no CAN controller |
| C2 | USB low-speed device | 1.5 Mbit/s | Enumerate, then vendor control OUT/IN transfers with 0..8 application bytes | Documented low-speed transceiver interface; USB host peer |
| C3 | Ethernet, MAC with external PHY | 10 Mbit/s | TX/RX valid untagged frames, initially 46-byte arbitrary payload, valid FCS | SNI PHY; line coding and clock recovery external, MAC remains firmware |

UART A1 is sequential TX then RX, not simultaneous full duplex. The peer waits
until the declared response window. RX-only operation can be armed ahead of a
burst. Unsolicited traffic outside the armed window is not accepted silently.

For JTAG, support non-byte-aligned scans and lengths across byte boundaries;
the initial runtime envelope is 1..512 bits if storage permits. IR length and
scan length come from the host. The model has a real TAP transition graph and
capture/update behavior; a loopback wire is insufficient.

For CAN, initial exchanges are on a controlled two-node bus. Add arbitration
loss and error/retry tests before declaring the experiment passed. Error
confinement/error-passive/bus-off behavior must be implemented or explicitly
identified as a remaining blocker; passing one clean frame is not a claim of
a compliant general CAN controller. Extended IDs, remote frames, and CAN FD
are later scope.

For USB, use endpoint zero control transfers to avoid accidentally selecting
bulk transfers, which are unavailable at low speed. Host-to-device OUT means
USB-host payload arriving at the ASIC; device-to-host IN means ASIC payload
returned to the USB host. Both are distinct from the ASIC's runtime controller.
Firmware must retain descriptors, address/configuration and data-toggle state
and perform setup/data/status phases. No external USB protocol controller.

For Ethernet, initial operation is full duplex with sequential TX/RX requests
on a controlled link. Half-duplex collision handling, IP/UDP/TCP, VLANs, and
maximum-size frames are later scope. The minimum untagged frame is 64 bytes
from destination address through FCS, not including preamble/SFD. The runtime
envelope therefore uses all 64 entries if complete frames are returned.
Preamble/SFD can be generated/checked while streaming and need not be stored.

## Transaction sequences and peer checks

| Protocol | Required sequence | Acceptance and failure injection |
|---|---|---|
| UART | Idle high; start, 8 LSB-first bits, stop for each TX byte; arm RX and detect start; sample data/stop; report data and status | Decode actual TX at peer bit centers; independent RX bytes; consecutive frames; phase sweep; +/-1% sender rate; false start, low stop, absent response, recovery |
| SPI | Set idle clock low and CS high; assert CS; present MOSI before rising edges; sample MISO; return clock low; deassert CS | Independent peripheral shifts varied bytes; check MSB order, setup/hold, exactly 8 clocks/byte, CS boundaries; lengths 1/2/63/64; repeated requests |
| I2C | START; address+W; register/data and ACKs; repeated START; address+R; read bytes; ACK intermediate bytes, NACK final byte; STOP | Resolved wired-AND pins; independent register map; address/data NACK, stretching at different phases, stuck bus timeout, STOP/release and retry recovery |
| JTAG | At least five TMS-high clocks; enter idle; Capture/Shift/Update IR; Capture/Shift/Update DR; return idle | TAP state and TDO checks on correct edges; lengths 1/7/8/9/31/32/33 and maximum; different instructions; invalid length rejection |
| SWD | Line reset/required selection; construct request; release turnaround; sample ACK; perform 32-bit data/parity phase; park/idle | Register readback with distinct values; OK/WAIT/FAULT; finite WAIT retry; parity fault; no output-enable overlap; subsequent good request after failure |
| PS/2 | Idle; host inhibit/request-to-send; device-clocked host frame; link ACK; receive device response frame; restore idle | Device model owns clock; odd parity/start/stop checks; distinguish wire ACK from response byte (e.g. 0xFA); variable clock, missing clock, parity fault and timeout recovery |
| CAN | Idle/SOF; arbitration/control; stuffed payload/CRC; delimiters/ACK/EOF/intermission; receive peer frame and ACK | Independent encoder/checker; 0/1/8-byte payloads; IDs and stuffing boundaries; CRC/stuff faults, absent ACK, arbitration loss, edge resynchronization, error recovery |
| USB | Bus reset; GET_DESCRIPTOR; SET_ADDRESS after status stage; configuration; vendor control OUT then IN; repeat | Host model validates token/data CRC, PID, NRZI/stuffing/EOP, response deadlines, toggles, duplicate retry behavior, malformed packets, reset/re-enumeration; no device ACK for invalid packets |
| Ethernet | Link ready; TX preamble/SFD, addresses/type, payload/pad, FCS; interframe gap; arm RX; receive independent frame and validate FCS | PHY-boundary peer checks bit order, CRC/FCS and minimum length; vary asynchronous RX clock phase; runt/corrupt/truncated/oversize frames; finite completion, overrun and next-frame recovery |

Each peer must check electrical ownership as well as data: open-drain protocols
must never drive a logic one; shared wires must have no conflicting drivers.
Simulation models should resolve pull-ups explicitly rather than feed back an
ideal pin state that hides drive conflicts. PHY/USB behavioral models do not
establish analog pad suitability or electrical compliance.

## Current-core resource assessment

Source inspection: [core](../src/protocol_core.v),
[storage](../src/runtime_store.v), [transport](../src/runtime_bridge.v),
[firmware ABI/controller](runtime.md). Reproduce source-bound firmware sizes and
arithmetic budgets with:

```sh
uv run python -m tools.exploration_budget > docs/exploration_budget.json
```

The checked-in [budget snapshot](exploration_budget.json) identifies input
hashes. It is not a protocol simulation or physical result.

| Resource | Current evidence / limit | Consequence to investigate |
|---|---|---|
| Program | 128 x 16-bit words; 7-bit PC; assembler rejects >128 words | ECHO/XOR dispatcher uses all 128; no spare space by appending code. Separate protocol images can replace it; test smaller request handlers before extending memory |
| Registers | Four 8-bit registers | Payload, loop count, pin state, parity/CRC and pointers compete; spills cost memory accesses |
| Data RAM | 256 bytes: 128 host parameters, 128 firmware scratch | Existing dispatcher stores request/event in 32 scratch bytes; different firmware can change that layout |
| Payload queues | 64 input bytes, 64 output data+metadata entries | One fully buffered request; host cannot feed input after commit; output entries need fresh metadata per commit |
| Record queues | One 16-byte submission and one 16-byte event | Firmware must consume submission/input before terminal publication; host must drain output before event retirement |
| Instruction timing | Most operations 1 cycle; memory/peripheral accesses 2; WAIT n takes n+1; WAITPIN can wait indefinitely | Firmware needs bounded polling for missing peers; WAITPIN alone cannot implement timeout recovery |
| Inputs | Two-flop synchronization before instruction sampling | Roughly two clocks plus sampling-instruction phase; inspect edge-to-observation schedules, not only bit periods; board CDC/MTBF remains open |
| Pins | Eight uio pins under firmware direction control; ui/uo occupied by loader/runtime | Each selected external interface must fit, or require an explicit generic pin/transport redesign |
| Physical baseline | 50 MHz, 79.15% utilization; +0.521 ns setup/+0.105 ns hold; 438 fanout violations | Prior mapped flow passed configured checks, not final signoff. Changes need new area/timing evidence; 8x4/SRAM are options, not assumptions |

### Cycle allowances, not performance claims

At a 50 MHz clock there are 20 ns per core cycle. These are total scheduling
allowances before sampling, branches, shifts, storage, and error checks consume
instructions. Host-controlled clocks may include documented inter-byte gaps;
UART/CAN/USB/Ethernet receive paths cannot pause their sender arbitrarily.

| Experiment | Core clocks per bit / clock period | First question |
|---|---:|---|
| UART 115200 | 434.028 | Can RX stop-bit handling and FIFO publication finish before the next start? |
| SPI / I2C / JTAG / SWD 100 kHz | 500 | Budget each half-cycle, synchronize inputs, and preserve direction turnaround |
| PS/2 model 12.5 kHz | 4000 | Observe both clock phases and retain bounded polling through host/device direction changes |
| CAN 125 kbit/s | 400 | Fit stuffing/CRC/arbitration and resynchronization without data-dependent bit drift |
| USB LS 1.5 Mbit/s | 33.333 | Fractional timing, receive alignment, CRC/stuffing and response deadlines must all fit |
| Ethernet SNI 10 Mbit/s | 5 | Capture variable receive bits and compute firmware FCS without losing subsequent bits |

### Per-experiment allocation budgets

These are initial allocation ceilings to test, not estimates that the code
will fit. Each firmware attempt starts with a 128-word code budget and must
report its actual assembled size, including request validation, completion,
and recovery. Keep over-budget drafts outside `firmware/*.asm` with their
reproduction command so the existing example-fit test stays meaningful.

The 32-byte request/event workspace below follows the current dispatcher only
as a starting allocation; protocol images may use another documented layout.
Parameters are host-owned and immutable while a request is pending. Scratch
is firmware-owned. Queue sizes are hardware limits, not software estimates.

| Experiment | Input/output queue envelope | Proposed scratch ceiling, including 32-byte request/event workspace | Additional storage question |
|---|---|---:|---|
| UART | 0..64 TX / 0..64 RX bytes | 48 bytes | Preserve receive count/deadline between frames; no full receive-burst scratch copy planned |
| SPI | 1..64 TX / equal RX count | 48 bytes | Keep shift state live while storing output; permit documented inter-byte gaps |
| I2C | <=64 command/write bytes / <=64 read bytes | 64 bytes | Reserve address/register/count/ACK/timeout state; define combined-transaction lengths before implementation |
| JTAG | <=64 packed TDI bytes / <=64 packed TDO bytes | 64 bytes | Scan bit count and final-byte validity metadata; no separate whole-scan scratch copy |
| SWD | One 4-byte write or read value plus parameter fields | 64 bytes | Track request parity, 32-bit data, retry counter and response state |
| PS/2 | One command with <=64 total input bytes / <=64 response bytes | 64 bytes | Device clock/deadline and parity state; receive buffer is bounded |
| CAN | 0..8 payload bytes each way; ID/length in parameters/metadata | 96 bytes | CRC/stuff counters, bit timing, arbitration retry data and error state; retransmission cannot reread popped input |
| USB | 0..8 application bytes per control exchange in either direction | 128 bytes | Descriptors, endpoint-zero setup/data/toggle state and retry copies may exceed RAM or code capacity |
| Ethernet | One 60-byte frame body TX / one 64-byte frame including FCS RX | 128 bytes | 32-bit FCS state, nibble/byte assembly and addresses; no spare whole-frame copy or continuous-receive guarantee |

Ethernet TX submits the 60-byte header/payload/padding body in the input FIFO;
firmware computes and appends the four-byte FCS.
RX returns all 64 frame bytes, including checked FCS, in this first experiment.
Firmware must not rely on the host generating FCS. USB descriptors may be
prepared in parameter memory, but live USB state and protocol processing
remain firmware responsibilities. Each exact image ABI is frozen before its
peer acceptance test; the UART ABI below is the first such contract.

Non-integer allowances require an explicit timing scheme. For UART a fixed
434-cycle period gives approximately 115207.4 baud; its small quantization
error does not eliminate peer clock mismatch or start-detection jitter. USB
needs its own legal sampling/transmit schedule, not an assumption that a
constant rounded bit period is acceptable.

### Host transport and storage budgets

READ8 uses five request/ack tokens; WRITE8 uses six. A 64-byte input takes 384
tokens; a submission plus commit takes 102; reading 64 data/metadata pairs and
popping them takes 1024; the terminal record takes another 80. These counts
exclude arguments, flush, polling, occupancy reads, and host timing delays.
Measure end-to-end bytes/s using the real adapter before promising throughput.
The simulated PinController's randomized delays are a test stimulus, not a
board bandwidth measurement.

Bounded requests must prebuffer all input, retain output until it can be
drained, and avoid needing mid-request parameter changes. Measure peripheral
service stalls while firmware publishes data. Test missing peers and full
queues, with bounded status reporting rather than an eternal wait. A 64-byte
queue cannot promise sustained Ethernet reception merely because one minimum
frame fits; unsolicited/back-to-back frames need explicit handling or a
documented receive window and overrun policy.

### Pin/PHY feasibility decisions

Each firmware image may assign its pins differently. Freeze these initial
assignments in each image's ABI before implementing its peer:

| Image | uio assignment (proposed) |
|---|---|
| UART | 0=TX, 1=RX; remaining pins released |
| SPI | 0=CS_n, 1=SCLK, 2=MOSI, 3=MISO |
| I2C | 4=SCL, 5=SDA, both open-drain |
| JTAG | 0=TCK, 1=TMS, 2=TDI, 3=TDO |
| SWD | 0=SWCLK, 1=SWDIO |
| PS/2 | 0=clock, 1=data, both open-drain |
| CAN | 0=TXD, 1=RXD; transceiver enable handled explicitly by board wiring or another pin |
| USB | TUSB1106:0=VP,1=VM,2=VPO,3=VMO,4=OE_n,5=SOFTCON;6..7 spare; SPEED/SUSPND strapped low |
| Ethernet SNI | 0=TXD, 1=TX_EN, 2=TX_CLK, 3=RXD, 4=RX_CLK, 5=CRS, 6=MDC, 7=MDIO |

For Ethernet select a PHY supporting a 10 Mbit serial network interface, such
as the TI DP83848 family. SNI fits the eight available protocol pins while
keeping the existing host transport. Four-bit MII needs more than eight pins
for its basic simultaneous TX/RX signals. SNI leaves Manchester coding and
clock recovery in the PHY; framing, FCS, receive decisions and buffering stay
instruction-driven. Document strap/reset/management wiring and validate exact
part timing before board use. MDIO management, if needed, is also firmware.
This is an interface selection, not a demonstrated PHY integration.

The USB study selects a TUSB1106 digital transceiver interface, with low-speed
operation, line-state visibility and controlled drive/release. Packet work
stays in firmware; no external controller is used. This interface selection
has no board interoperability or pad-timing proof. Do not infer connector
compliance from the packet model; see the study for the exact boundary and
the reproduced response-timing failure.

## First implementation milestone: UART TX/RX

**Deliverable:** a separate `firmware/uart_runtime.asm` image and pin-level
tests that send and receive runtime-supplied 8N1 bytes repeatedly through the
existing host interface, initially at 115200 baud. The ECHO/XOR image and its
tests remain available. Do not modify RTL until a concrete firmware attempt
demonstrates why it is needed.

The [UART runtime study](uart_runtime_study.md) now implements this contract on
the existing eight-register generic model and adds `test/test_uart_runtime.py`.
Its251-word candidate fails production assembly, so it remains in `study/`
rather than violating the production firmware-fit rule. The named production
image and mapped/board verification remain blocked; the107-word probe is unchanged.

### Specified firmware ABI (verified on the explicit model)

Use the existing 16-byte Request and Completion envelope from
[runtime v1](runtime.md). Operation numbers are local to the loaded image:
`1=TX`, `2=RX`, `3=TX_THEN_RX`. They do not become hardware operations.

All operations take arguments at parameter address zero, length four:

| Offset | Field | Rule |
|---|---|---|
| 0 | receive_count | 0..64; TX requires zero |
| 1 | timeout_windows | 1..255; one window is 65536 core clocks; response/next-start wait budget |
| 2..3 | reserved | Zero |

TX: input_count 0..64, output_limit zero. RX: input_count zero, output_limit
at least receive_count and at most 64. TX_THEN_RX: input_count 0..64 and the same
receive/output rules. Flags and request reserved bytes are zero. Request IDs
remain opaque and are returned unchanged. Invalid shapes are rejected before
driving TX or accepting RX data. Bad requests drain prebuffered input so a
terminal event can publish. Length zero has defined no-op behavior.

Use existing statuses 0..4 for OK/BAD_RECORD/BAD_OPERATION/BAD_ARGUMENTS/
BAD_LENGTH and reserve 5 for INTERNAL_FAILURE as in runtime v1. Proposed new
firmware statuses, now tested on the model: 6=RX_TIMEOUT, 7=FRAMING_ERROR. No transport error
code meanings change. Completion input_consumed counts bytes removed from the
input FIFO, including discarded input, matching RuntimeController.complete.
Output_produced counts published output entries, which can be less than the
requested receive count on failure. Detail is initially zero; reserved bytes
remain zero. Received bytes use metadata zero; do not publish a framing-error
byte as valid data. Preserve any preceding valid bytes.

Before publishing any partial failure, restore TX high and stop accepting the
failed response. A false start returns to the bounded start search. A framing
failure ends that request and requires RX high before accepting a new start;
a continuously low line must still allow a bounded failure completion. The
initial image reports a low stop bit as FRAMING_ERROR and a line that never
produces a qualified start before the deadline as RX_TIMEOUT. A distinct BREAK
diagnostic is deferred; neither error path may wait forever for line release.

### Timing and handshake

TX is idle high; RX is an independent input. Firmware validates and stages
the request, sends all TX bytes, then arms reception. The simulated peer waits
at least two UART bit periods after the last TX stop-bit end before responding.
For RX-only requests, the host may poll register diagnostic r3 at 0x010e for
`0xA5=RX_ARMED`; firmware reserves r3 for this value throughout its receive
window. Clear it outside that window. The test adapter starts a burst at
least two bit periods after observing RX_ARMED. This deliberate arming
contract avoids pretending the runtime can accept unsolicited traffic.

Nominal bit period: 434 core clocks. Count actual instruction overhead in
each TX and RX path. RX must detect/qualify start, sample near data centers,
validate stop, and service a following frame with no extra idle bits.
Bound the polling-loop detection jitter and account for synchronized input
latency. Support independently phased input and +/-1% sender mismatch.

Timeout windows represent a deadline in core clocks, not a count of
data-dependent iterations. One start-search deadline is timeout_windows times
65536 clocks; restart it after a valid byte. Detection/completion may exceed
the deadline by a documented bounded polling/publishing overhead. Every
detected frame also needs a finite completion bound so malformed traffic
cannot extend a request forever. If exact window accounting cannot fit the
current ISA, preserve the minimized attempt and propose a generic timer or
counted-poll solution before changing the ABI.

### Acceptance tests and commands

Planned test module: `test/test_uart_runtime.py`. It must load the image only
once per repeated-request scenario and exercise the public top-level pins,
with an independent UART decoder and sender rather than internal register
inspection for the payload. Diagnostic r3 is used only for arming.

1. TX 0/1/2/63/64 bytes, including 0x00/0xff/0x55/0xaa and seeded random data;
   verify framing, bit periods, no extra bytes, and TX idle before/after.
2. RX the same lengths with an independent sender; back-to-back frames;
   sweep input phase across one 20 ns core period and peer rates +/-1%.
3. TX_THEN_RX with different request/reply data; validate outputs, IDs,
   counts, status, and metadata. Repeat at least eight alternating requests
   without reset/reload; include maximum, zero-length, and failure recovery.
4. Inject short false start, invalid stop, continuously low line, missing
   first response, and a timeout between bytes. Check finite completion,
   partial counts and an immediately subsequent valid request.
5. Reject invalid operation, flags/reserved fields, argument length/range,
   mismatched buffered input and invalid output/receive lengths. Reject
   before line activity and prove ownership can be released afterward.
6. Interleave asynchronous host status reads while transferring; firmware
   timing must remain unchanged. Exercise reset during TX and RX; reload is
   required after reset, with pins released by reset.

The module now exists but cannot load on production. Use the study's explicit
model runner for its six groups. The following original production/mapped
commands remain future gates after resolving capacity:

```sh
uv run pytest -q test/test_assembler.py test/test_runtime_units.py test/test_runtime_driver.py
uv run make -B -C test COCOTB_TEST_MODULES=test_uart_runtime
uv run make -B -C test SIM=verilator COCOTB_TEST_MODULES=test_uart_runtime
uv run make -B -C test
```

Add the module to CI/default regression when implemented. Firmware-only
changes may use the existing mapped netlist after verifying its source hashes;
RTL changes require a new mapped netlist and fresh physical evidence. The
physical guide describes setup and gate commands. Record actual pass counts,
tool versions, firmware/source hashes and measured cycle traces.

## Work tracking and architectural decision gates

- [x] Archive organizer guidance.
- [x] Define all nine TX/RX experiments, acceptance contracts and order.
- [x] Assemble current firmware sizes and record arithmetic timing budgets.
- [x] Specify the first host-driven UART milestone.
- [x] Attempt UART runtime firmware; measure size and receive service paths
      (107-word probe; full validation/deadline acceptance still pending).
- [ ] Pass Wave A UART/SPI/I2C exchanges and failure recovery.
- [x] Reproduce I2C candidate capacity failure and test its TX/RX/recovery on
      an isolated larger-program model; production I2C capability remains open.
- [x] Attempt initial Wave B firmware/peers: production-RTL JTAG and explicit
      capacity-model SWD/PS2; preserve validation/mapped/hardware gaps.
- [x] Attempt Wave C CAN/USB/Ethernet, starting receive feasibility early;
      retain the differences between initial experiments and full acceptance.
- [x] Demonstrate CAN at 125 kbit/s standard-frame RX/live CRC/ACK on an explicit
      larger model; retain capacity blocker and outstanding TX/node behavior.
- [x] Demonstrate separate CAN TX/CRC/stuffing/monitoring/ACK and loss release;
      preserve 622-word combined-source capacity failure and missing node behavior.
- [x] Attempt USB packet RX/destuffing/CRC and diagnostic ACK; preserve failing
      response timing and program-capacity checks before attempting enumeration.
- [x] Prototype a generic larger-program/eight-register ISA in isolation; test
      combined CAN and legacy compatibility, and measure unmapped storage cost.
- [x] Test live USB decode/CRC and timed packet ACK using generic leaf subroutines;
      preserve buffered failures and distinguish packet timing from enumeration.
- [x] Test generic carry operations and compact USB firmware with addressed
      OUT/SETUP, software CRC5 and minimum token-to-data spacing on the model.
- [x] Test arbitrary USB IN payloads, firmware CRC/stuffing, host ACK/retry and
      alternating IN/OUT on one model image; preserve autonomous endpoint gaps.
- [x] Test live TX without waveform preparation and an autonomous vendor control
      write/status/read/status pair; preserve reset/standard-request/enum gaps.
- [x] Test qualified USB bus reset, deferred address commit and assigned-address
      vendor control transfers; preserve descriptor/configuration/enum gaps.
- [x] Demonstrate minimal USB enumeration plus arbitrary vendor traffic on the
      generic model, retaining request/jitter/physical limitations and a timing regression.
- [x] Test bounded Ethernet TX/RX, software FCS and PHY clock timing on a
      larger-program model; retain actual capacity and integration blockers.
- [ ] Resolve or preserve reproduced blockers for every experiment.
- [x] Audit all nine initial experiments, verify source/XML provenance and
      reproduce production size failures; distinguish missing features from blockers.
- [x] Verify the specified UART validation/deadline/reset contract on the generic
      model; preserve the measured251-word production failure without changing ABI.
- [x] Verify JTAG request/length rejection, input draining, pin/TAP preservation
      and subsequent valid scans on a198-word generic model candidate.
- [x] Test CAN missing-ACK active flags, three-attempt cap and subsequent RX on
      a701-word generic model candidate; preserve production capacity failure.
- [x] Demonstrate CAN arbitration-winner reception/ACK, retained-payload retry
      and shared attempt cap on an811-word generic model candidate.
- [x] Reproduce CAN fixed-clock drift failure and test bounded RX falling-edge
      phase correction on an819-word candidate; preserve full timing-rule limits.
- [x] Test persistent CAN counters, selected active/passive TX flags and bus-off/
      monitored recovery on a1,020-word call-model candidate; preserve failures.
- [x] Test timed CAN RX CRC/stuff/selected form flags and generic code compaction
      to1,021 words; preserve model-capacity and missing-flag failures.
- [x] Test CAN receiver first-post-flag and prolonged-dominant counter rules
      on the1,023-word model; preserve old-counter and size failures.
- [x] Reproduce CAN RX/TX active-flag bit-error counter gaps and preserve the
     1,076-word draft/model-capacity failure; draft behavior remains unverified.
- [x] Compact to1,024 words and verify selected active-flag bit-error counters,
      restarts and thresholds, with earlier counter/RX regressions preserved.
- [x] Reproduce CAN RX EOF/intermission/overload gaps and preserve a1,067-word
      draft/model-capacity failure, without claiming draft behavior.
- [ ] Make the RX tail workload executable; verify it and complete TX tails.
- [ ] Attempt remaining CAN counter/fault-confinement behavior;
      preserve full timing/continuous multi-node service limitations.
- [ ] Revalidate mapped behavior and physical implementation after RTL changes.
- [ ] Demonstrate hardware interoperability where equipment is available.

For every experiment maintain a result entry with firmware/peer source,
command/tool versions, selected rate, payload bounds, pin/wiring requirements,
measured program words and worst critical-path cycles, scratch/queue use,
host-service assumptions, outcomes and remaining limitations. No new protocol
is currently verified by this plan; historical examples retain their scope.

On failure: preserve the failing case; separate protocol bugs from program
capacity, throughput, buffering, host bandwidth and electrical constraints;
try a practical firmware solution; propose a generic extension; rerun all
earlier protocol regressions. Run synthesis for meaningful RTL changes and
full PnR at architectural checkpoints. Do not equate internal timing closure
with meeting external response deadlines. Scope cuts require an explicit
decision recorded in the README, with evidence and deferred behavior retained.

## Baseline validation

On 2026-10-24, before protocol implementation changes:

| Command | Actual result |
|---|---|
| `uv run --locked python -m tools.exploration_budget` | All four current images assembled; snapshot checked against a second invocation |
| `uv run --locked pytest -q test/test_assembler.py test/test_runtime_units.py test/test_runtime_driver.py` | 25 passed |
| `uv run --locked make -B -C test` | Five Icarus cocotb integration tests passed, zero failures/skips |
| `git diff --check` | Passed |

Environment: Python 3.12.4 in the locked project environment, pytest 8.4.2,
cocotb 2.0.1, Icarus 12.0 (Ubuntu package `12.0-2build2`). The commands used
`UV_CACHE_DIR=/tmp/asic-uv-cache` and PATH prefixes
`/tmp/asic-sim-packages/bin:/tmp/asic-sim-packages/iverilog/usr/bin` for a
temporary unpacked simulator; the iverilog wrapper supplied its local `-B`
library directory. A normal installed Icarus can use the commands directly.
The RTL results are in generated `test/results.xml`; these tests exercise the
existing runtime and narrow examples, not the planned nine TX/RX experiments.
No RTL, firmware, post-route netlist or physical metrics changed in this
planning milestone. Verilator, gates and PnR were not rerun for documentation.

## Reference material

Primary references for implementation; consult exact device timing and the
relevant specification chapters before freezing peer behavior:

- [NXP UM10204 I2C bus specification](https://cache.nxp.com/docs/en/user-guide/UM10204.pdf): bus transactions, open-drain behavior and timing.
- [TI SPI introduction](https://www.ti.com/video/6163521589001): controller/peripheral clock polarity and phase.
- [AMD TAP description](https://docs.amd.com/r/en-US/ug860-spartan-configuration/Test-Access-Port-TAP): JTAG pins and edge behavior.
- [Arm ADIv5 architecture specification](https://documentation-service.arm.com/static/622222b2e6f58973271ebc21): SWD request/data phases, turnaround, ACK/parity.
- [Microchip CAN documentation](https://onlinedocs.microchip.com/oxy/GUID-0C0B825F-9C9F-446F-AFDD-2324B355B920-en-US-12/GUID-275FACF3-A3EB-4FDA-B9DE-AAF310D41F8B.html): controller reference and links to Bosch protocol requirements; select a complete protocol reference before the CAN peer is accepted.
- [USB-IF USB 2.0 specification](https://www.usb.org/document-library/usb-20-specification): chapters 7–9 for signaling, packet/transaction and device requirements.
- [Microchip USB frames](https://developerhelp.microchip.com/xwiki/bin/view/applications/usb/how-it-works/frame/): low-speed transfer constraints.
- [TI DP83848 PHY datasheet](https://www.ti.com/lit/ds/symlink/dp83848-ep.pdf): MII/SNI signals, external clocking and PHY boundary.

UART framing is intentionally fixed to 8N1 in the first milestone. A specific
PS/2 device/reference and complete CAN/Ethernet normative coverage still need
selection before those peer models become acceptance evidence. These are
research tasks, not existing verification claims.
