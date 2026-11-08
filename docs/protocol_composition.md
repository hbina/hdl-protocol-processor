# Sequential protocol composition

`composition.rs` combines checked images on one engine. It does not introduce
concurrent engines or a Rust protocol frontend.

## Contract

Wrap each image in `Operation::new(name, program, successful_halt_addresses)`.
Every selected address must name a distinct HALT. `single_exit` is a convenience
for images with exactly one HALT; it rejects ambiguous multi-exit programs.
The caller is responsible for identifying semantic success: a valid HALT address
alone does not prove that it represents success.

`Composer::push` relocates JUMP, BRANCH_BIT and DEC_JUMP targets. At the next
append, only the preceding operation's selected successful HALTs become JUMPs to
the continuation. Other HALTs remain terminal, so timeout/error paths can stop
the sequence. Replacing HALT with JUMP preserves that instruction's one-cycle
cost. It does not eliminate the edge between protocol operations.

The composer conservatively derives pin claims from all instructions, including
input sampling and configuration. CAPTURE_INPUTS claims all eight input pins.
Operations on disjoint pins can follow directly. Reusing any active claim requires
an explicit `Handoff { release, clocks }` that releases the shared pins and
optionally waits. Only previously claimed pins may be released. A release emits
one CONFIGURE_PINS with enable/value zero; a positive delay emits WAIT. Pins from
older operations remain claimed until explicitly released, even when intervening
operations use other pins. These conservative claims are not an electrical proof.

Every append checks capacity before changing the composer. Failed appends leave
its existing sequence intact. The final image remains bounded to 256 words,
and `locations` records each operation's relocated entry for listings/debugging.

State is not reset between operations. Scratch data, flags, counters and outputs
follow each protocol's contract; the composer does not save/restore results or
infer scratch ownership. Plan shared scratch explicitly and satisfy each entry
condition. Pin handoff does not establish a safe clock domain, voltage or pad mode.

## Evidence and example

```sh
cargo run --locked -p bitlogic --example protocol_processor -- compose
```

The demo transmits UART `A` on pin 0, then performs SPI on pins 1..4. Tests check
24 independent combined waveforms across SPI modes and UART periods, including
shared-pin variants with an explicit release gap and received-byte reconstruction.
A polling-success/timeout pair checks that success reaches UART while timeout
halts before it. Other tests reject overlapping claims, invalid exits, bad
handoffs and capacity overflow, verify all branch relocation kinds and check an
exact 256-word sequence after a rejected append.

## Optional frontend decision

The plan makes an annotated Rust frontend optional. It is deferred: the checked
builder and composer now express the implemented examples, and runtime branching
is explicit in the ISA. No claim is made that arbitrary Rust loops or conditions
compile into target-side protocol control flow. A future frontend needs a distinct
host/runtime IR and independent cycle-preservation tests before replacing these
builders.
