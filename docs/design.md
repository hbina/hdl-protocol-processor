# Protocol Emulator v0.1 Baseline Design Report

This report records the original baseline. The current v0.2 runtime
architecture and programmer interface are specified in [runtime.md](runtime.md).
The root [README](../README.md) records current verification and physical results.

## 1. Objective and implementation status

Version 0.1 is a programmable, single-issue GPIO processor intended to prove
the architecture needed by the Jane Street protocol-emulator ASIC challenge.
The same synthesized processor executes three different uploaded programs:

- an 8N1 UART transmitter;
- an SPI mode-0 controller with simultaneous transmit and receive; and
- an open-drain I2C controller with ACK sampling and clock-stretch support.

Changing protocol does not change or resynthesize the RTL. A host stops the
processor, uploads a new program, and starts execution at address zero.

### Architectural invariant: protocols remain programmable

UART, SPI, I2C, and future protocol semantics must remain implemented in
uploaded firmware. The RTL may be extended with protocol-agnostic facilities
such as additional identical execution contexts, host-visible data queues,
timers, event capture, wider shifts, or atomic GPIO operations, but it must not
contain fixed-function state machines or control registers for a particular
protocol.

This distinction is central to the project: configurable UART, SPI, and I2C
blocks would form a conventional multi-protocol peripheral, whereas this design
is intended to remain a processor that can be reprogrammed for protocols not
anticipated when the RTL was created. Any proposed acceleration must therefore
be expressible and useful without naming a protocol in its hardware interface.

## 2. Architecture

```text
                   dedicated inputs ui_in[7:0]
                              |
                    +---------v----------+
                    |  program loader    |
                    |  3 x 6-bit chunks  |
                    +---------+----------+
                              |
                    +---------v----------+
                    | 64 x 16 program    |
                    | memory             |
                    +---------+----------+
                              |
       +-----------+----------v----------+-------------+
       |           | fetch / decode / execute           |
       | 6-bit PC  | 8-bit delay counter | halt state  |
       +-----------+----------------------+-------------+
                              |
                    +---------v----------+
                    | four 8-bit         |
                    | registers r0..r3   |
                    +----+-----------+---+
                         |           |
              +----------v--+     +--v----------------+
              | pin_out[7:0]|     | synchronized      |
              | pin_oe[7:0] |     | pin_in[7:0]       |
              +----------+--+     +--+----------------+
                         |           |
                         +-----+-----+
                               |
                     bidirectional uio pins
```

The core is deliberately not a conventional general-purpose CPU. It has no
stack, interrupts, or data memory. Its state and instruction set are centered
on deterministic GPIO changes, compact loops, bit shifting, input sampling,
and open-drain direction control.

### Programmer-visible state

| State | Width | Purpose |
|---|---:|---|
| `pc` | 6 bits | Addresses 64 program words |
| `r0`–`r3` | 8 bits each | Data, loop counters, masks, and constants |
| `pin_out` | 8 bits | Value presented to each output driver |
| `pin_oe` | 8 bits | `1` drives the pin; `0` releases it as input |
| delay counter | 8 bits | Implements cycle-counted waits |
| halt state | 1 bit | Freezes execution until configuration or reset |

Program memory is 64 words by 16 bits. In v0.1 it is expressed as an inferred
Verilog memory. The current CMOS5L mapping implements it with flip-flops rather
than an SRAM macro; the completed design contains 1,131 sequential cells in
total, including the program memory and processor state.

## 3. External interface

### Dedicated inputs and outputs

| Signal | Configuration mode (`ui_in[7]=1`) | Execution mode (`ui_in[7]=0`) |
|---|---|---|
| `ui_in[5:0]` | Six-bit program-data chunk | Bits 1:0 select debug register; bits 5:2 reserved |
| `ui_in[6]` | Synchronous write strobe | Reserved |
| `ui_in[7]` | Configuration mode | Must be zero to execute |
| `uo_out[7:0]` | `{next_word_address, chunk_index}` | Value of selected `r0`–`r3` |

The write strobe is sampled on the system clock. A host must hold each strobe
level for at least one complete clock cycle.

### Program-loading protocol

Each instruction is sent least-significant chunk first:

```text
chunk 0 = instruction[5:0]
chunk 1 = instruction[11:6]
chunk 2 = {2'b00, instruction[15:12]}
```

For each chunk, place data on `ui_in[5:0]`, pulse `ui_in[6]` high, and return it
low. The loader commits a word after chunk 2 and increments its word address.
Raising configuration mode restarts loading at address zero. While
configuration mode is high, the CPU and GPIO drivers are held in a safe reset
state but program memory is not erased. Lowering it starts the uploaded program
at address zero.

### Protocol pins

The eight `uio` pads have separate input, output, and output-enable paths:

```text
pin_out[i] ----> output value ----+
                                    > physical uio[i]
pin_oe[i]  ----> driver enable ---+

physical uio[i] ----> synchronizer ----> firmware input
```

`pin_oe=1` selects output; `pin_oe=0` releases the pad. This supports:

- push-pull signals by setting direction once and changing `pin_out`;
- open-drain signals by keeping `pin_out=0` and changing `pin_oe`; and
- input signals by clearing the corresponding output-enable bit.

All external inputs pass through a two-flop synchronizer. `IN`, `INBIT`, and
`WAITPIN` therefore observe a value delayed by two system clocks. Outputs change
only on rising system-clock edges.

## 4. Instruction encoding

Every instruction is one 16-bit word:

```text
15             12 11              8 7               0
+----------------+-----------------+------------------+
| opcode         | A / suboperation| immediate / B    |
+----------------+-----------------+------------------+
```

Unless noted otherwise, an instruction takes one clock. `WAIT n` takes one
instruction clock followed by `n` idle clocks. Branch targets are six bits.

| Opcode | Assembly | Effect |
|---:|---|---|
| `0` | `NOP` | Advance without changing state |
| `1` | `LDI rd, imm8` | Load an eight-bit constant |
| `2` | `IN rd` | Copy all synchronized inputs into a register |
| `3` | `OUT rs` | Copy a register to the output-value latch |
| `4` | `OE rs` | Copy a register to the output-enable latch |
| `5` | `SETO imm8` | Set the output-value latch immediately |
| `6` | `SETOE imm8` | Set the output-enable latch immediately |
| `7` | `WAIT imm8` | Delay for `imm8+1` instruction clocks total |
| `8` | `JMP addr6` | Unconditional branch |
| `9` | `JZ rd, addr6` | Branch when register equals zero |
| `A` | `DJNZ rd, addr6` | Decrement and branch when result is nonzero |

Opcode `B` performs register-to-register operations. `A[3:2]` selects the
operation, `A[1:0]` selects the destination, and bits 1:0 select the source.

| `A[3:2]` | Assembly | Effect |
|---:|---|---|
| `00` | `MOV rd, rs` | `rd = rs` |
| `01` | `XOR rd, rs` | `rd = rd ^ rs` |
| `10` | `OR rd, rs` | `rd = rd | rs` |
| `11` | `AND rd, rs` | `rd = rd & rs` |

Opcode `C` performs immediate arithmetic and logic:

| `A[3:2]` | Assembly | Effect |
|---:|---|---|
| `00` | `ADDI rd, imm8` | Add modulo 256 |
| `01` | `ANDI rd, imm8` | Immediate AND |
| `10` | `ORI rd, imm8` | Immediate OR |
| `11` | `XORI rd, imm8` | Immediate XOR |

Opcode `D` performs one-bit shifts and rotates:

| `A[3:2]` | Assembly | Effect |
|---:|---|---|
| `00` | `SHL rd` | Logical shift left |
| `01` | `SHR rd` | Logical shift right |
| `10` | `ROL rd` | Rotate left; old bit 7 becomes bit 0 |
| `11` | `ROR rd` | Rotate right; old bit 0 becomes bit 7 |

Opcode `E` accesses one pin. The pin number is encoded in bits 2:0:

| `A[3:2]` | Assembly | Effect |
|---:|---|---|
| `00` | `OUTBIT rs, pin` | Set `pin_out[pin]` from `rs[0]` |
| `01` | `INBIT rd, pin` | Set `rd[0]` from synchronized pin input |
| `10` | `OEBIT rs, pin` | Set `pin_oe[pin]` from `rs[0]` |
| `11` | `OEBITN rs, pin` | Set `pin_oe[pin]` from inverted `rs[0]` |

Opcode `F` contains control operations:

| Assembly | Effect |
|---|---|
| `HALT` | Stop fetching until reset or configuration mode |
| `WAITPIN pin, value` | Hold the PC until synchronized input equals value |

`OEBITN` is particularly important for open-drain serialization: a logical one
releases the line while a logical zero enables the zero-valued output driver.

## 5. Protocol implementations

### UART

`firmware/uart_tx.asm` configures pin 0 as push-pull TX and sends `0xA5`, least
significant bit first, with one start and one stop bit. At 50 MHz, instruction
overhead plus the programmed waits produces exactly 50 clocks per bit, or
1 Mbaud.

### SPI

`firmware/spi_mode0.asm` uses pin 1 for SCLK, pin 2 for MOSI, and pin 3 for
MISO. `ROL` moves the next transmit bit to bit zero for `OUTBIT`; `SHL` plus
`INBIT` assembles the received byte. Clock and data transitions implement SPI
mode 0 and MSB-first transfer.

### I2C

`firmware/i2c_write.asm` uses pin 4 for SCL and pin 5 for SDA. Both output
values remain zero. Firmware drives or releases the lines through output-enable
operations, which correctly models open-drain signaling. It generates START,
writes address byte `0xA0`, waits for SCL to rise after every release, and
samples ACK/NACK into `r3[0]`.

These pin assignments belong to the example programs, not the processor. A new
program may assign any instruction-accessible pin to any protocol role.

## 6. Assembler and firmware workflow

The Python assembler is dependency-free and runs inside the uv environment:

```sh
uv run python tools/assembler.py firmware/uart_tx.asm
uv run python tools/assembler.py firmware/spi_mode0.asm -o spi.hex
```

It resolves labels, validates registers, pin numbers, immediates, branch
addresses, and the 64-word capacity, then emits one hexadecimal word per line.
The cocotb loader uses the same assembler implementation as the command-line
tool, preventing test encodings from drifting away from documented firmware.

## 7. Verification performed

The cocotb regression uploads each program through the real external loader
interface and executes it on the same RTL instance. It verifies:

- UART framing for `0xA5` and the center of every 50-clock bit cell;
- eight SPI rising edges with MOSI sequence `10100101`;
- SPI receive assembly of `0xff` from a high MISO input;
- I2C START ordering, with SDA driven before SCL;
- open-drain direction state after the I2C ACK clock; and
- NACK capture through the synchronized input path.

Run the regression with:

```sh
uv sync --locked
uv run make -C test SIM=verilator
uv run pytest test/test_assembler.py
```

## 8. CMOS5L implementation results

The complete pinned LibreLane/IHP CMOS5L flow has synthesized, placed, clocked,
routed, and streamed out version 0.1 for the allocated 6-by-4 tile region. The
October 2026 local run produced these final metrics:

| Metric | Result |
|---|---:|
| Standard cells, excluding fillers | 7,403 |
| Standard-cell area | 132,373 µm² |
| Core area | 902,417 µm² |
| Placement utilization | 14.67% |
| Sequential cells | 1,131 |
| Worst setup slack at 20 ns | +6.943 ns |
| Worst hold slack | +0.120 ns |
| Setup/hold total negative slack | 0 / 0 ns |
| Final routing DRC errors | 0 |
| Magic DRC errors | 0 |
| LVS errors | 0 |
| Antenna-violating nets/pins | 0 / 0 |
| Disconnected pins | 0 |
| Maximum-fanout violations | 68 in each timing corner |

The mapped post-route netlist also passes the same cocotb UART, SPI, and I2C
firmware regression as the RTL. These results establish that the current design
fits comfortably, routes, and closes static timing in all three configured
process corners. The authoritative machine-readable results are in
`runs/wokwi/final/metrics.json` after a local hardening run.

The reported 4.24 mW power and approximately 0.01% IR drop are preliminary:
the run did not use activity vectors, and LibreLane warned that no voltage-source
locations were supplied for IR analysis. Magic DRC and LVS passed, but KLayout
DRC and layout XOR are disabled in the current challenge configuration. The
flow also used its generic fallback SDC because explicit PnR and signoff SDC
files are not configured. The final metrics additionally report 68
maximum-fanout violations in each timing corner; the affected nets and
constraints need review. These limitations should be resolved or accepted by
the official submission flow before calling the layout tapeout-ready.

## 9. Current limitations and next engineering steps

Version 0.1 now establishes functional programmability and a successful
physical implementation, but it is not yet final tapeout signoff. Important
remaining work includes:

1. Decide whether the 64x16 memory should remain flip-flops or use a latch-based
   memory or an available SRAM macro; the current implementation fits but the
   sequential logic occupies 55,406 µm².
2. Add explicit PnR/signoff timing constraints and confirm the intended Tiny
   Tapeout interface constraints rather than relying on fallback SDC.
3. Run or obtain the challenge's required KLayout DRC/XOR checks and improve
   power/IR analysis with realistic activity and voltage-source locations.
4. Define a physical host-side loader and reset procedure for the final board.
5. Add program-length protection or an explicit entry address; execution
   currently relies on firmware ending in `HALT`.
6. Expand verification with randomized instruction sequences and a software
   reference model of the complete processor.
7. Add assertions for PC bounds, loader chunk ordering, and open-drain safety.
8. Design protocol-agnostic concurrency for full-duplex and independently
   clocked work. Candidate solutions include multiple identical programmable
   contexts or a generic scheduling model; no context may be a fixed-function
   UART, SPI, I2C, or other protocol engine.
9. Prototype on an FPGA and test against physical UART, SPI, and I2C devices.

The most important architectural constraint is instruction throughput. Output
edges are deterministic, but instructions between two pin updates consume
cycles. Firmware must include that overhead when choosing `WAIT` values. Future
throughput improvements must preserve firmware-defined protocol behavior by
using generic programmable execution, timing, buffering, and GPIO facilities
rather than protocol-specific samplers, shifters, or state machines.
