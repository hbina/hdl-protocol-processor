# RHDL Protocol Processor

**Last updated: 2026-11-05.** A Rust workspace for two connected projects:

1. A clocked protocol processor implemented in [RHDL](https://github.com/samitbasu/rhdl).
2. Protocol implementations written in Rust that compile into processor instructions.

Development is moving to the separate RHDL Git checkout in `rhdl/`, on branch
`feature/protocol-processor`. The four protocol crates have been ported unchanged
and pass all ten tests and four doctests using local RHDL dependencies. Formatting,
protocol-scoped Clippy, Verilog export, and example generation pass there.
See its [dashboard](rhdl/README.md) and [porting notes](rhdl/docs/porting.md).
The fork must still be pushed and verified from a fresh remote clone; this
original project is retained until that verification succeeds. The nested checkout
is a separate repository and is not vendored into this repository's Git history.
The `rhdl/` directory is absent in this checkout as of 2026-11-05; new changes and
verification below apply to the root workspace.

The first vertical slice is UART transmission: Rust code emits a program, and
the RHDL processor executes it to drive a pin. This is a small starting ISA,
not a restored version of the earlier processor. The previous Python DSL,
NAND experiments, protocol studies, Tiny Tapeout integration, and physical-flow
tooling have been removed from the active project.

Protocols now use an RHDL-style `#[protocol]` macro: ordinary Rust functions with
local variables, loops, conditions and annotated helpers compile into a typed
effect IR and then processor instructions. The native function remains callable
inside a simulation capture. See the [frontend guide](docs/protocol_frontend.md).
Current protocol compilation specializes all arguments on the host. The processor
now supports input capture and bit computations; the protocol frontend does not
yet lower input-dependent execution or target-side branches.

```text
Rust protocol implementation → instruction image
                                      ↓
                         RHDL protocol processor → pins
                                      ↓
                         Verilog → FPGA/ASIC tools
```

## Run

Install a Rust toolchain supporting edition 2024 and Icarus Verilog (`iverilog`
and `vvp`). This workspace is tested with rustc/Cargo 1.99.0 and Icarus 12.0;
an older minimum Rust version has not been established. RHDL and `rhdl-fpga` are
pinned to Git revision `c99d5cc53269a247bbc675d0fbd766991d409f56`, with locked
transitive dependencies. The first Cargo build needs network access.

```sh
cargo test --workspace --locked
cargo run --locked -p protocol-compiler -- uart-tx \
  --pin 0 --cycles-per-bit 8 --text Hi --output build/uart.mem
cargo run --locked -p protocol-compiler -- uart-tx \
  --pin 0 --cycles-per-bit 8 --text Hi --format asm
mkdir -p build
cargo run --locked -p protocol-processor --bin export-processor \
  > build/protocol_processor.v
```

`uart.mem` contains one 32-bit instruction word per hexadecimal line, suitable
for `$readmemh`. The exported processor exposes an external instruction-fetch
interface; it does not load this file itself. The integration test supplies
program memory and checks execution. See [architecture and timing](docs/architecture.md)
and the [instruction contract](docs/isa.md).

## Source layout

| Crate | Responsibility |
|---|---|
| [`protocol-processor`](crates/protocol-processor/src/lib.rs) | RHDL state transition, explicit register bank, and named-port Verilog export |
| [`protocol-compiler`](crates/protocol-compiler/src/lib.rs) | Annotated Rust protocols, effect IR/lowering, native trace simulation and instruction-image CLI |
| [`protocol-isa`](crates/protocol-isa/src/lib.rs) | Shared instruction encoding, program validation, pin types, and independent cycle reference |
| [`protocol-macros`](crates/protocol-macros/src/lib.rs) | Rust syntax validation and generation of native/compiler companion paths |

## Status

| Protocol | Status | Evidence/scope |
|---|---|---|
| UART | Partial | Integer-cycle 8N1 transmit only; no receive, baud recovery, or board validation |
| SPI, I²C, JTAG, SWD, PS/2, USB, Ethernet, CAN | Not started | No implementations in this workspace |

| Check | Current evidence |
|---|---|
| Workspace regression | `cargo test --workspace --locked`: 12 tests and 4 doctests pass (3 compile-fail) |
| UART timing and masking | 6,144 programs (all 256 byte values × 8 pins × bit periods 1/2/8); 247,808 native cycle observations match an independent waveform oracle and reference machine |
| Compiled RHDL transition | 864 original boundary/malformed-word cases plus 240 bit-operation cases agree with the independent reference, RHIF/RTL interpreters, and two generated Verilog lowerings in Icarus |
| Clocked emitted processor | 1,454 cycle observations in Icarus; multi-byte UART, reset including active WAIT recovery, halt/fault, and final-PC behavior agree with the reference |
| Construction and CLI | All nonzero 16-bit WAIT encodings and all mask/value pairs checked; program limits, invalid pins/periods, CLI emission, and width mismatch rejection pass |
| Rust protocol frontend | Native Rust effects agree with IR for all 6,144 UART cases; helper/mutation/branch tests agree with instruction execution; zero/merged waits preserve elapsed clocks; syntax/type rejection and work limits checked |
| Tooling | `cargo fmt --all --check`, Clippy with warnings denied, `make emit`, and `make example` pass locally; Rust CI configured, not yet run remotely |

Exact scope and commands are in [verification](docs/verification.md).
Prior results do not validate this processor.

- [x] Establish a root Cargo workspace and pin RHDL.
- [x] Define a shared instruction ABI and bounded program image.
- [x] Implement `SET_PINS`, `WAIT`, and `HALT` in a clocked RHDL processor.
- [x] Implement a Rust UART transmitter that emits processor instructions.
- [x] Compile annotated Rust protocols through typed effect IR; expose native simulation, source inspection, and assembly listings.
- [x] Simplify waits while preserving protocol cycle timing.
- [x] Complete and record native, compiled-kernel, and emitted-hardware validation.
- [x] Add input capture, truth-table bit computations, and output-bit writes with explicit cycle contracts.
- [ ] Add target-side control flow to the timed protocol frontend.
- [ ] Add a program-memory integration and loading strategy for a selected target.
- [ ] Add more protocol implementations and protocol composition.
- [ ] Measure synthesis, placement/routing, timing, resources, and board behavior.

## Limits

The processor has eight input pins, eight output pins, 64 scratch bits, and an
eight-bit PC (256 instruction words).
Program memory must provide the addressed instruction combinationally; synchronous
block RAM needs a fetch stage and a revised timing contract. No instruction
branches, interrupts, runtime loader, bidirectional pads, or concurrent engines
exist yet. Programs are straight-line and terminate with `HALT`.
The frontend accepts a documented Rust subset and specializes source control
flow on the host; it does not yet lower runtime Rust variables or branches to
processor registers/instructions. Native simulation and compilation need matching
Rust arithmetic settings when expressions overflow.

The current register bank uses RHDL's FPGA DFF primitive, including its generated
initialization and synchronous reset. ASIC initialization support has not been
established. The pin interface exposes logic values, not electrical pad modes.
No FPGA bitstream, ASIC physical implementation, timing closure, or hardware
signoff is claimed. Types check representation and some construction errors;
they do not guarantee protocol correctness or efficient physical hardware.

## Previous project

The pre-reset committed tree is available at
`bd94857315fcb1038f4e4df8f9ac3ca477c2e0c2`:

```sh
git show bd94857315fcb1038f4e4df8f9ac3ca477c2e0c2:README.md
```

Uncommitted pre-reset source was additionally saved outside the repository at
`/tmp/jane-street-before-rhdl-reset-20261030/sources.tar.gz`, with a diff and
status record alongside it. This temporary backup is not durable Git history.
