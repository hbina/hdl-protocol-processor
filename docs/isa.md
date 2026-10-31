# Initial instruction ABI

Words are unsigned 32-bit integers, written as eight hexadecimal digits per line
in `.mem` files. The high nibble (`31:28`) is the opcode. This is an initial ABI;
there is no binary-container format or backward compatibility promise yet.

| Instruction | Encoding | Cycles and effect |
|---|---|---|
| SET_PINS | `0x1000MMVV` | One cycle. `pins = (pins & ~MM) | (VV & MM)`; PC increments |
| WAIT(N) | `0x2000NNNN`, N=1..65535 | Exactly N cycles including issue. On issue, PC increments and counter becomes N−1; later edges decrement the counter |
| HALT | `0xf0000000` | One cycle to enter halted state; outputs and PC then hold |

All reserved bits must be zero. Values outside a SET_PINS mask are ignored;
the host encoder canonicalizes those values to zero. WAIT(0), unknown opcodes,
and nonzero reserved bits set both fault and halted without changing the PC or
pins. HALT is permitted at PC=255; every instruction requiring PC increment
faults at that address rather than wrapping.

Reset overrides execution through the synchronous register bank. It clears PC,
wait counter, output values, halt, and fault. Software must not depend on a
nonzero idle pin value before reset/program initialization.

The `Program` constructor accepts 1..=256 instructions, requires a final HALT,
and rejects unreachable instructions after an earlier HALT. `Pin` accepts only
0..7 and `WAIT` uses `NonZeroU16`. Decoder validation still protects against
malformed raw instruction memory.
