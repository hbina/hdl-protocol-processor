> Historical architecture: superseded by [pin-v1](pin_processor.md).
> Results and instructions below apply to the previous design only.

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

The encoding is defined once, as the typed `Instruction` sum type in
`tools/isa.py`; the assembler, test programs and study generators all build
those values, and the table below is generated from it. Field conventions:

- `A[1:0]` is the destination (or stored) register `rd`; bits 1:0 of the
  immediate field are the source/address register `rs`.
- `A[3:2]` selects the operation within opcodes `1`–`4` and `B`–`E`.
- Branches to addresses 0–63 store the target in bits 5:0. Targets 64–127 set
  the long-branch bit 10 and store the full address in bits 7:0. `JMP`/`JFAIL`
  share opcode `8`; bit 11 selects `JFAIL` (branch when the flag is clear).
- `CMPI`, `CMPLT`, `CMPLTI` and the memory/peripheral operations set the
  condition flag; memory and peripheral operations take two clocks.

Unless noted otherwise, an instruction takes one clock. `WAIT n` takes one
instruction clock followed by `n` idle clocks.

<!-- isa:begin (generated by `uv run python -m tools.isa --doc`) -->
| Assembly | Example | Word | Opcode | `A[3:0]` | Effect |
|---|---|---:|---:|---:|---|
| `NOP` | `NOP` | `0000` | `0` | `0000` | Advance without changing state |
| `LDI` | `LDI r2, 165` | `12A5` | `1` | `0010` | `rd = imm8` |
| `CMPI` | `CMPI r2, 165` | `16A5` | `1` | `0110` | Flag = `rd == imm8` |
| `CMPLT` | `CMPLT r2, r3` | `1A03` | `1` | `1010` | Flag = `rd < rs` (unsigned) |
| `CMPLTI` | `CMPLTI r2, 165` | `1EA5` | `1` | `1110` | Flag = `rd < imm8` (unsigned) |
| `IN` | `IN r2` | `2200` | `2` | `0010` | `rd` = synchronized inputs |
| `LOAD` | `LOAD r2, r3` | `2603` | `2` | `0110` | `rd` = memory[`rs`]; flag = success; two clocks |
| `PREAD` | `PREAD r2, r3` | `2A03` | `2` | `1010` | `rd` = peripheral[`rs`]; flag = success; two clocks |
| `OUT` | `OUT r2` | `3200` | `3` | `0010` | Output-value latch = `rs` |
| `STORE` | `STORE r2, r3` | `3603` | `3` | `0110` | memory[`rs`] = `rd`; flag = success; two clocks |
| `PWRITE` | `PWRITE r2, r3` | `3A03` | `3` | `1010` | peripheral[`rs`] = `rd`; flag = success; two clocks |
| `OE` | `OE r2` | `4200` | `4` | `0010` | Output-enable latch = `rs` |
| `SETO` | `SETO 165` | `50A5` | `5` | `0000` | Output-value latch = `imm8` |
| `SETOE` | `SETOE 165` | `60A5` | `6` | `0000` | Output-enable latch = `imm8` |
| `WAIT` | `WAIT 165` | `70A5` | `7` | `0000` | Delay for `imm8+1` clocks total |
| `JMP` | `JMP 100` | `8464` | `8` | `0100` | Unconditional branch |
| `JFAIL` | `JFAIL 100` | `8C64` | `8` | `1100` | Branch when the flag is clear |
| `JZ` | `JZ r2, 100` | `9664` | `9` | `0110` | Branch when `rd == 0` |
| `DJNZ` | `DJNZ r2, 100` | `A664` | `A` | `0110` | Decrement `rd`; branch when the result is nonzero |
| `MOV` | `MOV r2, r3` | `B203` | `B` | `0010` | `rd = rs` |
| `XOR` | `XOR r2, r3` | `B603` | `B` | `0110` | `rd ^= rs` |
| `OR` | `OR r2, r3` | `BA03` | `B` | `1010` | `rd \|= rs` |
| `AND` | `AND r2, r3` | `BE03` | `B` | `1110` | `rd &= rs` |
| `ADDI` | `ADDI r2, 165` | `C2A5` | `C` | `0010` | `rd += imm8` (modulo 256) |
| `ANDI` | `ANDI r2, 165` | `C6A5` | `C` | `0110` | `rd &= imm8` |
| `ORI` | `ORI r2, 165` | `CAA5` | `C` | `1010` | `rd \|= imm8` |
| `XORI` | `XORI r2, 165` | `CEA5` | `C` | `1110` | `rd ^= imm8` |
| `SHL` | `SHL r2` | `D200` | `D` | `0010` | Logical shift left |
| `SHR` | `SHR r2` | `D600` | `D` | `0110` | Logical shift right |
| `ROL` | `ROL r2` | `DA00` | `D` | `1010` | Rotate left; old bit 7 becomes bit 0 |
| `ROR` | `ROR r2` | `DE00` | `D` | `1110` | Rotate right; old bit 0 becomes bit 7 |
| `OUTBIT` | `OUTBIT r2, 5` | `E205` | `E` | `0010` | `pin_out[pin] = rs[0]` |
| `INBIT` | `INBIT r2, 5` | `E605` | `E` | `0110` | `rd[0]` = synchronized `pin` input |
| `OEBIT` | `OEBIT r2, 5` | `EA05` | `E` | `1010` | `pin_oe[pin] = rs[0]` |
| `OEBITN` | `OEBITN r2, 5` | `EE05` | `E` | `1110` | `pin_oe[pin] = ~rs[0]` (open-drain helper) |
| `HALT` | `HALT` | `F000` | `F` | `0000` | Stop fetching until reset or configuration mode |
| `WAITPIN` | `WAITPIN 5, 1` | `F505` | `F` | `0101` | Hold the PC until the synchronized pin equals `value` |
<!-- isa:end -->

The isolated study models (`IsaConfig` values `wide256`, `wide512`,
`frontier`, `call_frontier` and `carry_frontier` in `tools/isa.py`) widen this
encoding: bit 8 of a long branch target sets bit 9 (`JMP`/`JFAIL`) or bit 11
(`JZ`/`DJNZ`); 18-bit words add bit 16 for `rd[2]` and bit 17 for `rs[2]`,
target bit 9 or the carry variant (`SHRC`, `RRC`); `JNC` is `JFAIL` with bit 8
set; `CALL addr10` is `0x400 | addr` and `RET` is `0x800`. None of these
extensions exist in the production RTL.

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

Instructions are values of the `Instruction` sum type in `tools/isa.py`
(`RegImm`, `RegReg`, `Jump`, `CondJump`, … plus one smart constructor per
mnemonic, such as `LDI(r0, 0xA5)`). `encode`/`decode` are exhaustive `match`
statements, checked by strict pyright, for each `IsaConfig` (production `BASE`
and the wider study models). `tools/program.py` builds programs from those
values: labels are objects, `pad_to` places far targets, `link` resolves labels
and checks capacity, and `to_asm`/`Image.disassemble` produce listings that the
text assembler parses back to the same words.

The text assembler (`tools/assembler.py`) only parses syntax into that model:

```sh
uv run python tools/assembler.py firmware/uart_tx.asm
uv run python tools/assembler.py firmware/spi_mode0.asm -o spi.hex
uv run python tools/assembler.py --disassemble firmware/uart_tx.asm
uv run python tools/assembler.py --isa carry_frontier study/protocol_exploration/usb_out_candidate.asm
```

It resolves labels and validates registers, pin numbers, immediates, branch
addresses and the 128-word production capacity, then emits one hexadecimal word
per line. Tests and the study generators construct `Program` values directly
instead of concatenating assembly text; the cocotb loader accepts the linked
`Image`. `test/golden/isa_words.json` pins every checked-in program's encoding
under every `IsaConfig`.

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
uv run pytest test/test_assembler.py test/test_isa.py test/test_program.py test/test_isa_golden.py test/test_isa_sync.py
uv run pyright
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
