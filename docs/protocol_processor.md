# Bitlogic protocol processor

Implemented as the `protocol_processor` Cargo example. The library generates the
combinational `processor_step`; `hdl/processor_top.v` supplies registers and reset.
No RHDL dependency or processor backend is involved.

## State and integration

State is PC (8 bits), wait counter (16 bits), pin values/enables (8 bits each), scratch bank
(64 bits), loop count (16 bits), and sticky halted/fault flags. Every rising
edge executes one transition. The wrapper has
an active-high synchronous reset that clears every state field; assert it before
execution. There is no initialization assumption or reset instruction.

The top exposes `clk`, `reset`, `instruction[31:0]`, `inputs[7:0]`, `pc[7:0]`,
`wait_remaining[15:0]`, `pins[7:0]`, `enables[7:0]`, `scratch[63:0]`, `count[15:0]`, `halted`
and `fault`. The integrator supplies synchronized input values and combinational
instruction memory at current PC and keeps the image stable during execution.
Synchronous memory needs a fetch stage and a revised timing contract.

Unused instruction words should be zero, which faults if executed. No loader,
interrupts, input synchronizers or target-specific memory primitive is supplied.
`hdl/pads.v` demonstrates logical tri-state integration: an enabled pin drives its
value; a disabled pin is high impedance. Pull-ups, IO cells, input synchronization
and electrical integration remain external. Reset clears enables and releases
every pad. HALT/fault preserve values and enables; reset or a protocol cleanup
sequence is required to release outputs. Open-drain programs use value=0 and
toggle enables, never driving a high level.

## Instruction ABI

32-bit words, eight hexadecimal digits per line for memory output. Opcode is
bits 31:28; bits not assigned below must be zero. This example ABI is versioned
through source control, with no binary compatibility promise yet.

| Instruction | Encoding | Effect |
|---|---|---|
| SET_PINS | `0x1000MMVV` | `pins = (pins & ~MM) | (VV & MM)`; PC increments |
| WAIT(N) | `0x2000NNNN` | N=1..65535; PC increments, counter becomes N-1 |
| EVAL_BIT | `0x30000000 \| dst<<16 \| lhs<<10 \| rhs<<4 \| table` | Read two six-bit scratch addresses; write six-bit destination with truth table bit `2*lhs_value+rhs_value`; PC increments |
| CAPTURE_INPUTS | `0x40000000` | Zero-extend inputs into scratch, clearing bits 8..63; PC increments |
| WRITE_BIT | `0x50000000 \| src<<3 \| pin` | Copy scratch bit 0..63 to output pin 0..7; PC increments |
| JUMP | `0x600000TT` | PC becomes target TT |
| BRANCH_BIT | `0x70000000 \| value<<14 \| src<<8 \| target` | Jump when scratch bit src equals value, otherwise PC increments |
| LOAD_COUNT | `0x8000NNNN` | Load 16-bit loop count, including zero; PC increments |
| DEC_JUMP | `0x900000TT` | Saturating decrement; jump to TT if old count >1, otherwise PC increments |
| SAMPLE_BIT | `0xa0000000 \| dst<<3 \| pin` | Copy input pin to one scratch bit, preserving the rest; PC increments |
| CONFIGURE_PINS | `0xb0MMEEVV` | Atomically update masked output values VV and enables EE; PC increments |
| SAMPLE_AND_SET | `0xc0000000 \| mask<<17 \| value<<9 \| dst<<3 \| pin` | Sample one input into scratch dst and update masked output values at the same edge; enables hold |
| PARITY_WORD | `0xd0000000 \| dst<<16` | XOR-reduce old scratch bits 32..63 into scratch dst, preserving other bits |
| HALT | `0xf0000000` | Set halted, hold PC and all other state |

Every instruction except WAIT consumes one cycle. WAIT consumes exactly N clocks including
issue: later waiting edges decrement the counter, ignoring instruction and input
changes. Execution resumes on the edge after the counter reaches zero.

Priority is wrapper reset, halted hold, active wait, decode/execute. Unknown
opcodes, nonzero reserved bits, WAIT(0), and any incrementing instruction at
PC=255 fault and halt. A taken jump at PC=255 is legal; an untaken branch or
fall-through DEC_JUMP faults there. A fault sets both flags and preserves PC,
wait, pins, enables, scratch and count;
no partial instruction effects occur. HALT at PC=255 is legal. Fault is sticky;
even injected fault=true/halted=false states preserve fault during execution.

SET_PINS ignores values outside its mask. Host encoders canonicalize those bits.
CONFIGURE_PINS masks both EE and VV with MM; bits 27:24 must be zero. SET_PINS
and WRITE_BIT update values only and preserve enables. UART TX and SPI use an
initial CONFIGURE_PINS in place of their first SET_PINS to enable outputs without
adding a clock. SPI also explicitly releases its MISO pin. This extends the
prototype ABI while retaining the documented UART/SPI waveforms and image sizes.
SAMPLE_AND_SET reserves bits 27:25 and samples pre-edge input values before
registered output changes; masked values are canonicalized by the host. PARITY_WORD
uses a six-bit destination, reserving bits 27:22 and 15:0. Its source is read
before writing, including destination aliases in the upper word. Both new
instructions consume one cycle and obey normal wait/halt/fault/final-PC rules.
The parity reduction uses existing constant shifts/XOR in bitlogic; no library
language extension is needed. The unoptimized SWD read builder occupied 274 words
even with atomic sampling; replacing 33 parity instructions with PARITY_WORD
reduced it to 241–242 words, within the existing PC capacity.
The checked `Program` requires 1..=256 instructions, a final HALT, and every
branch target inside the image. Code after an earlier HALT is permitted because
branches can reach it. This supersedes the initial straight-line validation rule.
No termination proof is claimed. Raw memory is still validated by execution;
hardware targets are any eight-bit address, including unused words that fault.

EVAL_BIT reads both sources before writing even when destination aliases a source.
Truth tables are four-bit values; register/pin/table host constructors reject
invalid widths. CAPTURE_INPUTS retains its historical whole-bank overwrite
contract. SAMPLE_BIT is an extension needed to retain earlier samples when
receiving multi-bit data. Inputs are consumed at the execution edge; input
synchronization and its latency are external.

Dynamic selection uses bounded 64-way decoder expansion in the existing DSL.
`stats` reports 2,314 IR nodes and 107,058 bytes of combinational Verilog for this
revision. This measures source/graph size, not synthesized gates or timing.

## Hand-worked edge traces

Observations are immediately after the named rising edge. Before edge 1, reset
has established zero state. `P` means the value before the instruction.

| Program | Edge | PC | Counter | Pins | Halt/fault |
|---|---|---|---|---|---|
| WAIT(1); SET_PINS(1,1); HALT | 1 | 1 | 0 | 0 | 0/0 |
| same | 2 | 2 | 0 | 1 | 0/0 |
| same | 3 | 2 | 0 | 1 | 1/0 |
| WAIT(2); SET_PINS(1,1); HALT | 1 | 1 | 1 | 0 | 0/0 |
| same | 2 | 1 | 0 | 0 | 0/0 |
| same | 3 | 2 | 0 | 1 | 0/0 |
| same | 4 | 2 | 0 | 1 | 1/0 |
| WAIT(0) at PC=7, not waiting | issue | 7 | 0 | P | 1/1 |
| SET_PINS at PC=255, not waiting | issue | 255 | 0 | P | 1/1 |
| HALT at PC=255, not waiting | issue | 255 | 0 | P | 1/0 |

A reset edge overrides waiting, halted and fault states, returning all fields to
zero. The next non-reset edge fetches word zero; reset itself executes no word.

## Commands

```sh
cargo run --locked -p bitlogic --example protocol_processor -- demo Hi 0 8
cargo run --locked -p bitlogic --example protocol_processor -- mem Hi 0 8
cargo run --locked -p bitlogic --example protocol_processor -- asm Hi 0 8
cargo run --locked -p bitlogic --example protocol_processor -- verilog
cargo run --locked -p bitlogic --example protocol_processor -- stats
cargo run --locked -p bitlogic --example protocol_processor -- poll 0 4 2
cargo run --locked -p bitlogic --example protocol_processor -- spi a5 0 4
cargo run --locked -p bitlogic --example protocol_processor -- uart-rx 0 16 8
cargo run --locked -p bitlogic --example protocol_processor -- i2c 50 read 2
cargo run --locked -p bitlogic --example protocol_processor -- jtag ir a5 8
cargo run --locked -p bitlogic --example protocol_processor -- ps2 a5 2 4
cargo run --locked -p bitlogic --example protocol_processor -- swd read 0
cargo run --locked -p bitlogic --example protocol_processor -- swd reset
cargo run --locked -p bitlogic --example protocol_processor -- jtag-pair a 4 12345678 32
cargo run --locked -p bitlogic --example protocol_processor -- uart-rx-batch 2 0 16
cargo run --locked -p bitlogic --example protocol_processor -- compose
```

The demo verifies every observed state against IR evaluation and the independent
integer reference. Tests additionally check independent protocol waveforms.
The poll demo uses low inputs and reports timeout; the SPI demo receives zero;
the RX demo uses low inputs and reports a framing error. I²C reports bus busy,
PS/2 times out on inhibit, SWD reports invalid ACK, and JTAG captures zeros. Protocol status is in
scratch, separate from processor fault. These demos exercise execution without a
physical peer. The native runner reports Halted, Fault or Limit; limits bound simulation rather
than proving program termination. See [protocol interfaces](protocols.md),
[verification evidence](verification.md), and the [remaining plan](protocol_processor_plan.md).

## Host assembly

`assembler.rs` supplies checked labels, forward/backward branches, nonzero WAIT
emission (zero delay emits nothing), scratch constants and image validation.
Duplicate/unbound labels, out-of-range targets and oversized images are errors.
I²C and PS/2 use it for runtime polling and error cleanup. This is host assembly,
not a Rust protocol frontend. [Sequential composition](protocol_composition.md)
preserves selected successful exits and explicit pin handoff. Optional synthesis
and mapped-netlist checks are documented in the [synthesis baseline](processor_synthesis.md).
