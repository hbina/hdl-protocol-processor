# Initial instruction ABI

Words are unsigned 32-bit integers, written as eight hexadecimal digits per line
in `.mem` files. The high nibble (`31:28`) is the opcode. This is an initial ABI;
there is no binary-container format or backward compatibility promise yet.

| Instruction | Encoding | Cycles and effect |
|---|---|---|
| SET_PINS | `0x1000MMVV` | One cycle. `pins = (pins & ~MM) | (VV & MM)`; PC increments |
| WAIT(N) | `0x2000NNNN`, N=1..65535 | Exactly N cycles including issue. On issue, PC increments and counter becomes N−1; later edges decrement the counter |
| EVAL_BIT | `0x30000000 \| (dst<<16) \| (lhs<<10) \| (rhs<<4) \| table` | One cycle. Six-bit scratch addresses, four-bit table. `r[dst] = (table >> (2*r[lhs]+r[rhs])) & 1`, reading operands before the write; PC increments |
| CAPTURE_INPUTS | `0x40000000` | One cycle. Zero-extend the eight input pins into the 64-bit scratch bank; PC increments |
| WRITE_BIT | `0x50000000 \| (src<<3) \| pin` | One cycle. Write scratch bit `src` (0..63) into output pin `pin` (0..7), preserving other output pins; PC increments |
| HALT | `0xf0000000` | One cycle to enter halted state; outputs and PC then hold |

All reserved bits must be zero. Values outside a SET_PINS mask are ignored;
the host encoder canonicalizes those values to zero. WAIT(0), unknown opcodes,
and nonzero reserved bits set both fault and halted without changing the PC or
pins. HALT is permitted at PC=255; every instruction requiring PC increment
faults at that address rather than wrapping.

Reset overrides execution through the synchronous register bank. It clears PC,
wait counter, scratch bits, output values, halt, and fault. Software must not depend on a
nonzero idle pin value before reset/program initialization.

The `Program` constructor accepts 1..=256 instructions, requires a final HALT,
and rejects unreachable instructions after an earlier HALT. `Pin` accepts only
0..7 and `WAIT` uses `NonZeroU16`. Decoder validation still protects against
malformed raw instruction memory.

`Program::new` also checks bit-register addresses, truth-table width, and output
pin operands before accepting typed instructions. EVAL_BIT reserves payload bits
27:22; WRITE_BIT reserves 27:9. Every new instruction obeys the existing halt,
wait, and final-PC rules. `Machine::tick_with_inputs` models the input port;
`tick` remains shorthand with zero inputs. The RHDL `step_with_inputs` kernel
provides the corresponding transition; `step` retains the zero-input wrapper.
