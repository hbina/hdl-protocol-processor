# Autonomous pin processor: pin-v1

This is an incompatible replacement for the queue/request architecture.
Protocols execute as uploaded instructions; there is no host communication
layer during execution. The hardware contains a 256×16 program memory, four
8-bit registers, a condition flag, an 8-bit PC and wait counter, 256 bytes of
private RAM, synchronized inputs, and independent output-value/enable latches.
No stack, interrupts, peripheral bus, host queues, or fixed protocol engines exist.

## Pins and wrapper

`INPUT_PINS` and `OUTPUT_PINS` independently accept 1..256. Pins are numbered
from zero in separate input/output spaces. Every input has two synchronizer
flops, running even when execution is paused. An instruction samples the
previous synchronized value at its execution edge: a stable transition needs
two synchronizer edges before the following instruction edge can observe it.
Outputs change only at clock edges. No bypass or edge-capture hardware is provided.

The Tiny Tapeout wrapper maps input 0..7 to uio[0..7], input 8..14 to ui[0..6],
output 0..7 to uio[0..7], and output 8..15 to uo[0..7]. Only the uio pads have
physical output enables; dedicated uo pads always drive their value. Their
logical enable bits are writable but do not disable dedicated physical outputs.
Open drain uses output value zero and switches the corresponding uio enable.

ui[7] selects configuration. During configuration ui[5:0] carries data,
ui[6] is the write strobe, and uo reports loader status. During execution these
pins become ordinary inputs/outputs; there is no acknowledgement or response token.

## Loading, reset, pause, and halt

For cold boot hold reset low and ui=0x80 before supplying clocks. Keep
configuration high while releasing reset. Transfer each instruction as three
six-bit chunks, low bits first, pulsing ui[6] high then low for each chunk;
maintain every level for at least one full clock. Only the low four bits of
the final chunk are used. After the final strobe is low for a full clock,
lower ui[7] to start at PC=0. Software must upload at most 256 words and count
them: the loader cursor wraps at 256, and the eight-bit loader status remains
`{cursor[5:0], chunk[1:0]}` with a truncated address display. Pad unused program
locations with HALT when control flow could reach them.

Reset/configuration clear registers, condition, PC, wait state, and output
values/enables. They do not erase RAM or program memory. A new rising
configuration mode restarts the loader. A mode held high through reset starts
loading at address zero. Configuration is board-clocked, not asynchronous.

`ena` pauses issue and wait countdown; an already-issued RAM access completes
its commit clock even if ena falls. Reset or configuration cancels a pending
RAM access. HALT and invalid instructions freeze execution and hold output
values/enables until reset/configuration. The PC wraps from 255 to 0.

## Instructions and timing

Registers and immediates are eight bits. `LOAD rd, ra` and `STORE rs, ra`
access all RAM addresses, taking exactly two clocks (issue/commit). Address and
write data are captured at issue; LOAD may use the same register for address
and destination. Successful accesses set the condition flag. Comparisons
replace that flag; other instructions leave it unchanged. JFAIL branches when
it is false. All normal instructions/branches cost one clock, taken or not.
WAIT n occupies n+1 enabled clocks. WAITPIN occupies at least one enabled clock
and stalls until its condition is met; implement timeouts with firmware polling.

`INBIT rd, pin` replaces the ENTIRE register with zero or one. `OUTBIT rs, pin`
sets one output latch from rs bit zero. OEBIT writes an output enable; OEBITN
writes its inverse. The pin operand may be a number 0..255 or an index register.
Register operands, including aliases, are sampled before writes.
`WAITPIN pin, value` uses an immediate or register-selected input and literal
value zero or one.

`IN rd, bank`, `OUT rs, bank`, and `OE rs, bank` access banks of eight pins.
Bank is an immediate, 0..31. Partial input banks zero-fill high bits; partial
output banks affect only existing pins. LDI followed by OUT/OE replaces the
old SETO/SETOE instructions. GPIO writes do not alter the condition flag.

Bad immediate indices are rejected by the assembler for the chosen pin counts.
Dynamic indices are checked by hardware. Invalid indices, unused banks, and
reserved/noncanonical encodings halt at the offending PC with no instruction
side effects. Reset state has condition=false. All program words must be canonical.

## Encoding

Words are `major[15:12] | A[11:8] | immediate[7:0]`. For ordinary register
operations A is `{selector[1:0], rd[1:0]}`. Register-source encodings use only
immediate bits 1:0; remaining immediate bits must be zero. Unary shifts require
immediate=0. Bank numbers occupy immediate. Immediate pins occupy all eight
immediate bits; indexed pins use only bits 1:0. JZ/DJNZ require A[3:2]=0.
WAITPIN uses A=4+value for immediate pins and A=8+value for indexed pins.
All branch targets are full eight-bit addresses without short/long variants.
Opcode 0x6 and every unlisted encoding are reserved.

| Instruction | Major opcode | Selector |
|---|---|---|
| LDI | 0x1 | 0 |
| CMPI | 0x1 | 1 |
| CMPLTI | 0x1 | 3 |
| ADDI | 0xc | 0 |
| ANDI | 0xc | 1 |
| ORI | 0xc | 2 |
| XORI | 0xc | 3 |
| MOV | 0xb | 0 |
| XOR | 0xb | 1 |
| OR | 0xb | 2 |
| AND | 0xb | 3 |
| CMPLT | 0x1 | 2 |
| LOAD | 0x2 | 1 |
| STORE | 0x3 | 1 |
| SHL | 0xd | 0 |
| SHR | 0xd | 1 |
| ROL | 0xd | 2 |
| ROR | 0xd | 3 |
| OUTBIT immediate / register | 0xe / 0x5 | 0 |
| INBIT immediate / register | 0xe / 0x5 | 1 |
| OEBIT immediate / register | 0xe / 0x5 | 2 |
| OEBITN immediate / register | 0xe / 0x5 | 3 |
| IN bank | 0x4 | 0 |
| OUT bank | 0x4 | 1 |
| OE bank | 0x4 | 2 |
| NOP | 0x0 | canonical word 0x0000 |
| WAIT | 0x7 | operand A = 0 |
| JMP / JFAIL | 0x8 | operand A = 0 / 8 |
| JZ / DJNZ | 0x9 / 0xa | A = register |
| HALT | 0xf | canonical word 0xf000 |
| WAITPIN immediate / register | 0xf | A = 4+value / 8+value |

## Tools and examples

`tools/isa.py` is the typed encoding/decoding definition. `tools/program.py`
links labels, and `tools/assembler.py` parses handwritten assembly and generated
listings. Python generators and executable test fixtures build typed instructions
directly; see the [construction audit](typed_instruction_audit.md). Default pin counts match
the wrapper (15 inputs, 16 outputs). For another hardware configuration:

```sh
uv run --locked python -m tools.assembler program.asm --input-pins 256 --output-pins 256
uv run --locked python -m tools.isa --doc
uv run --locked python -m tools.snapshot_isa
```

Generate generic synthesis measurements with `uv run --locked python -m tools.check_pin_synthesis`
(or supply `--yosys /path/to/yowasp-yosys`).

No historical ISA variants or compatibility aliases are provided. The new
`test/golden/pin_words.json` snapshot covers only active firmware, including the three standalone UART listings; the old
snapshot was removed and is recoverable through [Git history](source_history.md). See [examples](../firmware/README.md).

## Validation boundary

Core RTL checks cover every 16-bit word against the typed decoder for five
pin configurations, full RAM access, instruction timing, invalid operations,
reset/pause, and full loader/PC boundaries. Pin-only wrapper tests can run
unchanged on RTL and a newly mapped netlist. Historical netlists are incompatible.
The production wrapper remains a 50 MHz, 6×4 CMOS5L target. Physical results
must be regenerated; see the README for current status.


## Continuous UART firmware

[UART programs](../firmware/uart/README.md) demonstrate RAM-backed repeating TX,
continuous bounded RX and sequential echo entirely in firmware. No ISA, RTL, queue
or host transport was added. READY and error reporting use ordinary GPIO. The
sequential echo program requires a cooperative sender and does not implement
simultaneous full-duplex traffic. See the UART guide and root README for evidence
and the remaining physical/interoperability limitations.
