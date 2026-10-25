# Generic runtime interface v1

The default ASIC contains a 128x16 instruction memory, four 8-bit registers,
256 bytes of data memory, a 64-byte input FIFO, a 64-entry output FIFO (data
byte plus opaque metadata byte), and depth-one 16-byte submission/event FIFOs.
The RTL never decodes request operations or firmware result codes. This is a
bounded runtime foundation; it does not implement complete protocols or
concurrent execution.

## Ownership and publication

The external controller prepares all input and parameters before publishing
one submission. Only one request may be outstanding. Submission commit locks
parameter writes and host input pushes until the host consumes the final
terminal-event byte. That final pop requires an empty output FIFO. Submission
and event staging are invisible until all 16 bytes are committed. Output entries
require fresh data and metadata staging before each commit.

Data addresses 0x00..0x7f are host-prepared parameters, readable by firmware.
Addresses 0x80..0xff are private firmware scratch. Firmware cannot write the
parameter region, and the host cannot access scratch. Data and program contents
are not reset; initialize storage before reading it. Configuration/reset clears
queues, staging, partial transport state, registers, PC, and GPIO drivers.
Idle flush clears queues/staging without changing data memory or execution.

All accesses occur in the core clock domain. Firmware has priority over a held
host transaction. Memory/FIFO mutation controls use local direction, ownership,
and capacity checks; the shared error-report decoder does not feed those write
controls. Instructions that access memory/peripherals take exactly two
clocks: issue and commit. A failed access leaves the destination/storage intact
and clears the condition flag. Host arbitration never stalls firmware. `ena` stops instruction issue; an
already-issued access always completes its second cycle, even if `ena` falls.
This preserves exactly-once queue effects across pause/resume. Reset or
configuration aborts pending access and clears the runtime channel. FIFO
acceptance uses pre-edge occupancy: a full FIFO rejects a push even if a pop
occurs on that edge, and an empty FIFO rejects a simultaneous pop.

## Pin transport

Configuration (`ui_in[7]=1`) retains the original synchronous rising write
strobe (`ui_in[6]`) and three 6-bit instruction chunks. It still requires board
clock timing. The loader now accepts 128 words; output status reports the low
six cursor bits and chunk index, wrapping its displayed address after 64 words.
Count uploaded words in software; more than 128 words wraps the actual cursor.
Execution PC now wraps at 128. Existing examples end in HALT and keep their
encodings/timing; previous implicit PC rollover at 64 is not preserved.

For safe cold boot, assert reset and hold `ui_in=0x80` (configuration high,
write/request low) before supplying clocks. Keep configuration high when
releasing reset, upload the complete program, return the write strobe low for
one full clock, then lower configuration to execute. Program memory is not
initialized by reset; never enable execution before loading valid firmware.
Runtime entry starts with request/acknowledgement zero.

Runtime (`ui_in[7]=0`) assigns inputs 5:0 to a token and input 6 to a request
toggle. Outputs are `{acknowledgement_toggle, error, response_token[5:0]}`.
Drive the token no later than the request toggle and hold it until acknowledgement.
Two request synchronizer flops plus an explicit settling cycle precede capture.
Wait at least one 20 ns core period after observing matching acknowledgement
before sampling the response; the board controller must handle acknowledgement
synchronization in its own clock domain. No new request may be sent until the
previous response is sampled. Enter runtime with request low; raising
configuration mode or reset abandons all partial transactions.

Runtime reads/writes use six-bit tokens:

- READ8: opcode 0, address bits 5:0, 11:6, 15:12, zero continuation token.
  The final address acknowledgement returns data bits 5:0; continuation returns
  bits 7:6. The byte is captured and its side effect applied exactly once.
- WRITE8: opcode 1, three address tokens, data bits 5:0, data bits 7:6.
  Only the final token commits a write. Successful write responses are zero.
- Unused upper token bits must be zero. Errors acknowledge the token and reset
  the byte-transaction parser; record staging is unchanged. There is no automatic
  retry after timeout because the final write might already have committed.

Error codes: 1 invalid opcode, 2 invalid encoding/value, 3 unmapped address,
4 denied direction/ownership, 5 empty, 6 full, 7 incomplete staging, 8 busy.

## Address map

Peripheral addresses are accessible to firmware at 0x0100 plus an 8-bit register
value. Direction restrictions apply even if the access is otherwise well formed.

| Address | Access | Meaning |
|---|---|---|
| 0000..007f | Host RW, firmware R | Parameter memory; host writes only while idle |
| 0080..00ff | Firmware RW | Private scratch |
| 0100 | Host W | Value 1 flushes runtime queues/staging while idle |
| 0101 | R | Bits 0..4: pending, input available, output available, submission available, event available |
| 0102..0105 | R | Input, output, submission, event occupancy |
| 0106..010a | R | Version=1, program words=128, payload depth=64, record bytes=16, parameter bytes=128 |
| 010b..010e | R | Generic register diagnostics r0..r3; runtime debug replaces old pin selection |
| 0110 | Host W | Push input byte, only while idle |
| 0111 | Firmware R | Pop input byte while pending |
| 0120 | Host W | Append submission byte while idle |
| 0121 | Host W | Value 0 commits complete submission; requires empty result queues |
| 0122 | Firmware R | Pop next submission byte; final byte retires record |
| 0130, 0131 | Firmware W | Stage output data and opaque metadata while pending |
| 0132 | Firmware W | Value 0 commits staged output entry |
| 0133, 0134 | Host R | Peek output data and metadata |
| 0135 | Host W | Value 0 pops output entry |
| 0140 | Firmware W | Append event byte while pending |
| 0141 | Firmware W | Value 0 commits complete event; input/submission must be consumed |
| 0142 | Host R | Pop next event byte; final byte releases ownership after output is drained |

Writes to read-only ports, nonzero commit/pop values, and undefined addresses
fail without modifying storage. Output/event publication is disallowed after a
terminal event becomes available. Partially staged output is discarded on
terminal-event retirement.

## ISA extensions

All instructions remain 16 bits. Register fields remain two bits. LOAD/STORE
and PREAD/PWRITE take a data register followed by an address register; STORE's
first operand is the source (e.g. `STORE r0, r1`). Memory operation immediate
bits 7:2 must be zero. Invalid memory encodings halt execution.

| Instruction | Base word before register/immediate fields | Effect |
|---|---|---|
| LOAD rd, ra | 2400 | Read data memory through ra |
| STORE rs, ra | 3400 | Write data memory through ra |
| PREAD rd, ra | 2800 | Read peripheral 0100+ra |
| PWRITE rs, ra | 3800 | Write peripheral 0100+ra |
| CMPI rd, imm8 | 1400 | Condition = rd equals immediate |
| CMPLT rd, rs | 1800 | Condition = unsigned rd < rs |
| CMPLTI rd, imm8 | 1c00 | Condition = unsigned rd < immediate |
| JFAIL addr | 8800 short / 8c00 long | Branch when condition is false |

Comparisons and branches take one clock. Only new accesses/comparisons change
the condition flag. The assembler emits existing short JMP/JZ/DJNZ encodings
for addresses 0..63; for 64..127 it adds bit 10 and uses the seven-bit target.
Unsigned comparisons let bounded firmware validate lengths without lengthy
software subtraction loops. The runtime dispatcher occupies all 128 words.

## Firmware ABI

Multibyte fields are little endian; hardware does not interpret them.

Submission (16 bytes):
`request_id:u16, operation:u8, flags:u8, arguments_address:u16,
arguments_length:u16, input_count:u16, output_limit:u16, reserved:4 bytes`.

Terminal event (16 bytes):
`request_id:u16, kind:u8, status:u8, input_consumed:u16,
output_produced:u16, detail:u16, reserved:6 bytes`.

`firmware/runtime.asm` supports 1=ECHO (zero address/length) and 2=XOR (one
parameter byte). Both return zero metadata. Inputs must be fully buffered,
counts at most 64, and output limit sufficient for all input. Flags/reserved
bytes must be zero. The selected bounded ABI rejects nonzero high bytes of
address/length/count fields as BAD_RECORD; low-byte range/layout errors use
BAD_ARGUMENTS or BAD_LENGTH. XOR parameters must be in 0..127.

Events use kind 1=TERMINAL and statuses 0=OK, 1=BAD_RECORD, 2=BAD_OPERATION,
3=BAD_ARGUMENTS, 4=BAD_LENGTH. Code 5 is reserved for future INTERNAL_FAILURE
reporting; the current validated bounded path does not emit it. Detail and
reserved bytes are zero. Rejected requests discard buffered input before
reporting. Input consumed counts bytes removed, including discarded bytes;
output produced counts published entries, not protocol-pin completion.

The controller writes parameters/input, appends and commits the submission,
waits for event availability, drains outputs, then reads the terminal event.
It cannot modify parameters in flight. Updates between requests are supported;
mid-request reconfiguration and request cancellation are not implemented.

## Python controller

`tools.runtime.RuntimeController` accepts an async `exchange(token)` callback.
The board adapter owns request/acknowledgement GPIO timing and raises
TransportError with the returned error code. `test/test.py` provides a simulated
pin adapter with randomized asynchronous request timing and response settling.
Calls on one controller must be serialized by the caller.

```python
controller = RuntimeController(exchange)
caps = await controller.capabilities()
request = Request(
    42, 2, arguments_address=17, arguments_length=1, input_count=4, output_limit=4
)
await controller.submit(request, b"abcd", arguments=b"\xa5")
output, completion = await controller.complete(request)
```

Submission validates field widths/lengths before changing hardware, checks idle
state, and flushes idle staging. Partial submission failure leaves the controller outstanding. Any transfer
timeout, canceled transfer, or I/O failure marks it unusable, including during
the initial idle check: reset/reload hardware and construct a new controller.
No operation is automatically retransmitted. Completion validates ID, kind, reserved bytes, counts, and the requested
output limit. Large jobs can be split into independent <=64-byte
requests; this does not preserve protocol transaction framing across requests.

## Verification and remaining work

Unit verification covers simultaneous FIFO access at depths 1/3/4/64, pointer
wrap, byte/metadata pairing, partial record visibility, ownership, denied
access, and terminal-event backpressure. Pin-level RTL tests cover ECHO/XOR,
malformed requests/transfers, loader/branch boundaries, failed instruction
accesses, reset recovery, and UART timing during asynchronous host activity.
See README.md for current RTL, mapped-netlist, and physical-flow results.

The memory/queues currently map to standard cells. Timing exceptions isolate
only the asynchronous request's first synchronizer D pin; held token data
retains conservative single-cycle timing and a 16 ns max-delay constraint.
Physical board validation, CDC/MTBF signoff, streamed payloads, additional
contexts, complete protocols, and realistic power/IR analysis remain open.
