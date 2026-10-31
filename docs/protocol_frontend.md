# Rust protocol frontend

Protocol authors write ordinary Rust syntax in functions annotated with
`#[protocol]`. They use `drive(Pin, bool)` and `wait(u16)` for timed effects;
they do not construct `Instruction` values or manipulate an instruction builder.

```rust
use protocol_compiler::{protocol, drive, wait, simulate, Pin};

#[protocol]
fn pulse(pin: Pin, count: u8) {
    let mut high = true;
    for _ in 0..count {
        drive(pin, high);
        wait(3);
        high = !high;
    }
}

let pin = Pin::new(0).unwrap();
let program = pulse::compile(pin, 2).unwrap();
println!("{}", program.to_assembly());
let native = simulate(|| pulse(pin, 2)).unwrap();
assert_eq!(native.effects.as_slice(), pulse::ir(pin, 2).unwrap().effects());
```

The listing is:

```text
000: SET_PINS 0x01, 0x01
001: WAIT 3
002: SET_PINS 0x01, 0x00
003: WAIT 3
004: HALT
```

Each drive takes one clock, so the example holds each level for four clocks:
one drive cycle plus three wait cycles. Pure Rust computations take no target
cycles. They execute on the host while specializing the protocol.

## Two generated paths

The procedural macro parses the function using `syn` and validates the supported
syntax. It retains the original Rust function and generates a same-named marker
type in Rust's type namespace, with these associated methods:

- `pulse::compile(...)`: specialize arguments, lower the effect IR, and validate
  the final instruction image.
- `pulse::ir(...)`: inspect the ordered effects before instruction lowering.
- `pulse::source()`: inspect normalized captured Rust source.

`pulse(...)` remains the native function. Use it inside `simulate(|| ...)` to
capture its drive/wait effects without instruction lowering. The capture is
thread-local, rejects nesting, and clears itself when a native panic unwinds.
Calling timed effects outside simulation is an error (a panic).

At macro expansion, timed calls are rewritten into typed IR-emission code.
Calls to other annotated helpers use their generated emitters and share the
same IR; there is no processor-side call instruction or intermediate HALT.
Rust compiles both paths and checks their types. The generated emitter retains
Rust control flow and expressions, so arithmetic, casts, borrowing, and type
inference are performed by Rust rather than reimplemented in an interpreter.

```text
annotated Rust syntax
    ├── native Rust function → simulated effects
    └── generated Rust emitter → specialized effect IR → instructions
```

This uses the macro-plus-companion approach discussed for RHDL, but is a
separate frontend and backend. It does not reuse RHDL's hardware compiler, and
does not capture a full runtime Rust AST for reinterpretation. Captured source
is inspection metadata; the ordered effect IR is the current transformation
boundary.

## Supported subset and boundaries

The initial subset supports local bindings and mutation, expressions, `if`,
`match`, bounded `for` loops, and unqualified calls to annotated protocol helpers.
Parameters may be `Pin`, `NonZeroU16`, `bool`, unsigned integers (`u8/u16/u32/u64/usize`),
or `&[u8]`. Import the named types directly; aliases and qualified parameter
types are not recognized by this syntax checker. Functions have no return-type
annotation and return unit. Only `.get()` and `.len()` method calls are supported.

The macro rejects `while`/`loop`, early exits (`return`, `break`, `continue`, `?`),
closures, async/unsafe constructs, body macros, mutable-reference parameters,
generics, nested items, and qualified helper calls. Direct recursion is rejected;
helper nesting is bounded to 32 calls during compilation. Compilation also caps
loop iterations and emitted effects at 65,536 each. These caps do not replace
the final 256-word instruction-memory check. The `__protocol_` binding prefix
is reserved. The crate must be imported as `protocol_compiler` for generated paths.

Native simulation runs the original Rust code; compilation's loop/call guards
do not constrain native computation. Rust arithmetic/indexing behavior and
panics remain ordinary Rust behavior. The frontend is not a sandbox.

**All arguments and control conditions are currently host-time values.**
Loops expand and branches specialize before execution on the processor. Changing
the bytes or a parameter requires compiling a new image. This is not a compiler
for arbitrary Rust machine code. Target-side variables, arithmetic, runtime
branches, input sampling, and receive protocols require further ISA/backend work.

## Timing-preserving lowering

The compiler removes zero waits and merges adjacent waits. Runs longer than
65,535 clocks are split into legal WAIT operands without losing elapsed clocks.
It retains repeated drives even if the output value does not change, because
removing a drive would remove a target clock. A single HALT is appended at the
end of the complete program. The transformations preserve pin values and elapsed
cycles, not instruction addresses or intermediate wait-counter values.

## UART and command line

The actual UART implementation is now an annotated `uart_tx` function calling an
annotated `uart_bit` helper. Native Rust simulation, emitted IR and the existing
waveform/hardware tests exercise it. Its integer-cycle timing contract is unchanged.

```sh
cargo run --locked -p protocol-compiler -- uart-tx \
    --pin 0 --cycles-per-bit 8 --text Hi --format asm
```

Use `--format memh` (the default) for a loadable instruction image and `--output`
to write either format to a file. Assembly output is a human-readable listing;
an assembly-text parser is not implemented.
