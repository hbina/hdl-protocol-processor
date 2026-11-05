# Processor and protocol compiler

This project separates target-side execution from host-side protocol compilation.
The processor is synthesized from RHDL. Protocols use ordinary Rust syntax in
`#[protocol]` functions. The macro preserves native execution and generates a
typed effect emitter; the companion `uart_tx::compile(...)` method specializes
arguments and lowers the effects into instructions. Authors do not construct
instructions manually. See the [Rust frontend](protocol_frontend.md) for its
syntax, generated paths, timing rules, and current host-time specialization limit.

## Processor

`State` contains an eight-bit PC, sixteen-bit wait counter, eight output values,
64 scratch bits, and sticky halted/fault flags. The pure RHDL `step_with_inputs`
kernel computes next state (`step` supplies zero inputs).
`Processor` connects it to an explicit `rhdl-fpga::DFF<State>` register bank.
Local Rust mutation describes combinational next-state logic, not extra cycles.

The generated top-level ports are:

| Port | Direction | Meaning |
|---|---|---|
| `clk` | Input | Rising-edge execution clock |
| `reset` | Input | Active-high synchronous reset; returns all state to zero |
| `instruction[31:0]` | Input | Word at the current PC, supplied by external combinational memory |
| `inputs[7:0]` | Input | Input values sampled by CAPTURE_INPUTS; top-level integration owns synchronization |
| `pc[7:0]` | Output | Current fetch address |
| `wait_remaining[15:0]` | Output | Remaining hold cycles after WAIT issue |
| `pins[7:0]` | Output | Registered pin values |
| `halted`, `fault` | Output | Sticky execution status, cleared by reset |

Each rising edge performs one transition. If halted, state holds. If waiting,
only the counter decrements and the instruction input is ignored. Otherwise,
the processor decodes the current word. Fetch/decode are combinational within
the cycle; the next instruction is not executed at the same edge.

Memory is an explicit integration boundary. The initial HDL regression uses a
256-word array with `instruction = rom[pc]`. No target memory or loader is implied.
An image must remain stable while executing; runtime writes are unspecified.

## UART transmitter

`protocol_compiler::uart_tx::compile` accepts bytes, a checked pin index, and a nonzero
integer number of processor clocks per bit. It emits one idle-high bit interval,
then a start bit, eight data bits LSB first, and a stop bit for each byte.
Only the chosen pin is modified. The final instruction is HALT; the line stays high.

A bit interval of N cycles uses SET_PINS (one cycle) followed by WAIT(N−1).
For N=1, WAIT is omitted. Thus the next bit transition occurs exactly N clocks
later. The compiler does not round clock frequencies to baud rates: the caller
must choose an integer period and assess the resulting baud error.

This unrolled transmitter is intentionally simple. At N>1, B bytes require
`2*(1+10*B)+1` words, so at most twelve bytes fit in the current image.
At N=1 the limit is twenty-five bytes. Larger programs are rejected, not truncated.
An empty payload is allowed and emits idle plus HALT. This is not an efficient
general-purpose protocol engine yet; runtime protocol loops and buffering need
their own ISA and timing design. Input capture and bit computations now exist
in the processor ISA; the timed protocol frontend still specializes all arguments
on the host.

## Development direction

Readability and explicit behavior come first: typed pins, nonzero wait durations,
checked program capacity, and an independent reference model constrain mistakes.
Future instruction changes must update the encoder, reference, hardware decoder,
cycle contract, and differential tests together. Protocol safety and electrical
behavior cannot be inferred from Rust types alone.

Keep target hardware separate from host compilation. Preserve RHDL intermediate
representations for future optimization experiments if useful; do not assume that
more transformations imply faster routed hardware. Measure a selected target
before making area, throughput, or timing claims.
