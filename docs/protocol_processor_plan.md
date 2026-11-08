# Protocol processor implementation plan

Plan recorded: 2026-11-07. Progress updated: 2026-11-08. The stage descriptions
define intended work; the progress table distinguishes implementation from plans.

| Stage | Current progress and evidence |
|---|---|
| 1–5 | Complete for the initial processor/UART TX slice; [architecture](protocol_processor.md), [protocol interfaces](protocols.md), and [exact verification evidence](verification.md) |
| 6 | Input capture, scratch computations and output-bit writes implemented and tested; SAMPLE_BIT added to retain earlier received bits |
| 7 | Jumps, scratch-bit branches, saturating loop counter and bounded polling implemented; native/IR/clocked-HDL timeout and data-dependent traces pass |
| 8 | Example roles implemented with independent peers: SPI, complete bounded adjacent-frame UART RX, I²C, state-preserving JTAG sequences, SWD and PS/2 device TX; [feasibility study](protocol_feasibility.md) selects CAN/USB/Ethernet boundaries; documented protocol limits remain |
| 9 | Checked builder and [sequential composition](protocol_composition.md) implemented, with successful exits, relocation, pin handoff and independent waveforms/results; optional annotated frontend considered and deferred |
| 10 | [Generic mapping](processor_synthesis.md) and a [routed SKY130 HD block study](sky130_implementation.md) complete with explicit memory/IO/clock assumptions, extracted TT timing, constraint/router checks and routed functional regression; chip-level signoff remains separate work |

Functional checks and the single-corner block implementation are distinct evidence.
No chip-level physical or electrical signoff is claimed. The documented protocol
limits remain part of scope. See the [requirement-by-requirement audit](processor_plan_audit.md).

## Step-by-step execution guide

Use the stages below in dependency order. Their progress table records existing
work; use the same checkpoints when changing the processor or extending a protocol.

| Step | Deliverable | Check before proceeding |
|---|---|---|
| 1. Freeze the cycle contract | Instruction encodings, state layout, reset/hold/fault rules, WAIT timing and memory interface | Hand-worked boundary traces have one unambiguous expected result |
| 2. Build the software oracle | Checked instruction/image types and an independent integer reference machine | Exact encodings, invalid words, capacity and execution-limit tests pass |
| 3. Implement the processor in bitlogic | A pure `processor_step(current_state, instruction, inputs)` next-state function | Native Rust and IR evaluation agree with the independent reference |
| 4. Add the clocked wrapper | Generated combinational Verilog, state registers, synchronous reset and testbench ROM | Icarus post-edge traces match the reference, including reset and fetch boundaries |
| 5. Complete UART TX first | Checked byte-to-program builder, listing/demo and expected pin waveform | Byte values, pins, periods and capacity boundaries pass through native, IR and clocked HDL |
| 6. Add input and scratch operations | Capture, truth-table evaluation and scratch-to-pin writes | Independent tests cover aliases, preservation and malformed encodings across all execution paths |
| 7. Add reactive execution | Branches, jumps, bounded counters, timeout polling and observable results/errors | Taken/untaken branches, changing inputs and timeout edges have matching cycle traces |
| 8. Add protocols one at a time | SPI → UART RX → I²C → JTAG → SWD → selected PS/2 role | Each has a written timing/role contract, independent peer, normal/error cases and HDL checks |
| 9. Compose operations | Shared assembler, relocation, explicit successful exits and pin handoff | Combined operations preserve results, ownership and total timing; invalid compositions are rejected |
| 10. Measure a selected target | Synthesis, clock/IO constraints and a physical implementation study | Record measured area/timing and constraint checks separately from functional evidence and chip signoff |

For each protocol in step 8, first choose its role, modes, transfer size, pin
ownership and result/error layout. Then calculate its instruction schedule and
input-synchronization budget before choosing a rate. Implement the builder and an
independent peer, exercise success and failure paths, and only then add its demo
and documented support claim. CAN, USB and Ethernet start with feasibility studies
and dedicated-controller/PHY decisions rather than an assumed bit-banging design.

Keep each change reviewable: update the encoding contract, reference model,
bitlogic core and HDL tests together when adding an instruction. Run the required
workspace checks listed under Completion rules, then update README and verification
evidence. Prefer completing the UART TX vertical slice before widening the ISA;
defer the optional annotated frontend until the builders and composition work.

## Goal and architecture

Build an example processor using `bitlogic`, then protocol programs that execute
on it. The first complete demonstration is UART 8N1 transmission from a checked
instruction image to a verified pin waveform.

```text
Rust protocol builder -> checked instruction image
                                  |
                                  v
current state + instruction + sampled inputs
                    |
           #[logic] processor_step
                    |
          next state + pin controls
                    |
      caller-owned registers and program memory
```

The library remains untimed and combinational. A Rust runner and a small Verilog
top module independently supply state feedback. Clock, reset, synchronization,
pad cells, and electrical behavior remain top-module responsibilities. This is a
library example, not a restored processor backend or an RHDL dependency.

Use historical commit `0e6e0b4c`, especially its `docs/isa.md` and
`docs/architecture.md`, as a contract reference. Historical results do not verify
the new implementation.

## Proposed layout

Register one Cargo example with `test = true` so workspace tests include it:

```text
crates/bitlogic/examples/protocol_processor/
  main.rs                 demo, image/listing output, HDL emission
  isa.rs                  typed instructions, encoding, image validation
  reference.rs            independent cycle model
  core.rs                 #[logic] next-state function
  runner.rs               native execution and traces
  protocols/
    mod.rs
    uart.rs               first protocol builder
  hdl/
    processor_top.v       registers, synchronous reset, core instance
  tests.rs                native, IR, HDL, and waveform regressions
docs/
  protocol_processor.md   implemented architecture and cycle contract
  protocols.md            implemented protocol interfaces and limitations
```

Create files as their stages begin. Keep planned behavior separate from documented
implemented behavior. Extract a host tooling crate later if reuse warrants it.

## Stage 1: Specify the initial processor

Start with the historical dimensions and straight-line instruction subset:

| Field | Proposed size / behavior |
|---|---|
| Instruction | 32 bits; opcode in bits 31:28 |
| Program counter | 8 bits; at most 256 words |
| Wait counter | 16 bits |
| Output values / input values | Eight bits each |
| Scratch bank | 64 bits; added in stage 6 |
| Status | Sticky halted and fault flags |
| Reset | Active-high synchronous reset; clears all state |

| Instruction | Encoding | Cycle contract |
|---|---|---|
| `SET_PINS(mask, value)` | `0x1000MMVV` | Update masked outputs and advance PC in one cycle |
| `WAIT(N)` | `0x2000NNNN` | N=1..65535; consume exactly N clocks including issue |
| `HALT` | `0xf0000000` | Enter halted state in one cycle; hold PC and outputs |

1. Write the architecture and complete encoding/reserved-bit specification.
2. Define priority: wrapper reset, halted hold, active wait, instruction execution.
   WAIT advances PC on issue and loads N-1; waiting edges only decrement the
   counter. The next instruction executes at the edge after it reaches zero.
3. Fault and halt on unknown opcodes, nonzero reserved bits, WAIT(0), and any
   instruction that would increment PC=255. HALT remains legal at PC=255.
   Faults must not partially execute an instruction; document every state field.
4. Ignore SET_PINS values outside the mask; canonicalize them in the encoder.
5. Specify combinational instruction memory addressed by current PC, stable for
   the run. No synchronous-RAM fetch stage or runtime loader is implied.
6. Define traces as state immediately after each rising edge, including reset.

**Exit evidence:** encoding tables and hand-worked WAIT(1), WAIT(2), HALT,
malformed-word and final-PC traces in the architecture document.

## Stage 2: Implement checked instructions and the reference machine

1. Add typed pin indices, nonzero waits, instructions, and a bounded program image.
2. For the initial ISA require 1..=256 words, a final HALT, and no code after an
   earlier HALT. Reject excess capacity without truncation.
3. Implement encoding and raw-word validation. Test exact expected words, not
   just encoder/decoder round trips.
4. Implement a plain Rust cycle model with ordinary integers, independent of
   `Bits`, the IR and the hardware decoder. Do not share execution helpers with
   the implementation being checked.
5. Add a runner with explicit halt/fault outcomes and an execution limit.

**Exit evidence:** independent tests for instruction effects, malformed words,
every valid WAIT duration, mask/value combinations, reset, and image/PC limits.
No generated hardware support is claimed yet.

## Stage 3: Implement the bitlogic processor step

1. Expose separate `Bits<N>` and `bool` ports for current/next state, instruction,
   and inputs. The current macro does not support struct ports.
2. Give every output a default before conditionals. Implement hold, wait and
   decode priority; the step function itself has no clock or reset.
3. Decode fields with constant slices and masks using existing DSL features.
4. Compare native function results and IR evaluation with the reference machine.
5. Check complete execution sequences plus injected boundary states, including
   ignored instructions while waiting/halted and PC=254/255 behavior.

Prefer an implementation within the current DSL. If an essential operation needs
a library extension, specify the smallest change and independently verify its
native, IR and HDL semantics before relying on it.

**Exit evidence:** reference/native/IR agreement over a documented test space.
Finite transition tests are not exhaustive over the entire machine state space.

## Stage 4: Integrate and test clocked HDL

1. Emit the combinational module through `to_verilog()`.
2. Add state registers and synchronous reset in a small top module. Do not rely
   on initialization statements for behavior after power-up.
3. Supply a testbench ROM addressed by PC; define unused words and test execution
   reaching them. Keep memory integration separate from the generated core.
4. Run Icarus and compare post-edge state/pins against independent reference
   traces for complete programs as well as single transitions.
5. Reset during execution, WAIT, HALT and fault; verify restart and reset priority.

**Exit evidence:** generated combinational HDL and clocked-wrapper regressions
pass, including fetch alignment. These establish functional simulation only.

## Stage 5: Deliver UART transmit

1. Add a Rust builder accepting bytes, an output pin, and integer clocks per bit.
2. Emit one idle-high interval, then start, eight LSB-first data bits and stop for
   each byte. Finish with HALT and the line high.
3. For a bit interval of N clocks emit SET_PINS followed by WAIT(N-1); omit WAIT
   when N=1. Count instruction execution in the waveform schedule.
4. Check image capacity. This initial unrolled builder uses
   `2*(1+10*byte_count)+1` words for N>1 and `1+10*byte_count+1` for N=1.
   Test empty payloads and exact acceptance/rejection boundaries.
5. Add demo, image/assembly output, and HDL emission commands. Show the cycle/pin
   trace and document how the top module supplies memory and reset.
6. Check all byte values, all eight pins, and periods 1/2/8 against an independent
   waveform oracle. Include multi-byte frames, period boundaries, and preservation
   of other pins. Exercise the same behaviors in clocked HDL.

Baud is processor frequency divided by the chosen period. Reject unsupported
parameters; do not silently round. Record baud-error assessment as a target
integration task. UART receive is a separate milestone.

**Exit evidence:** reference, native, IR and clocked HDL agree with expected UART
transitions and durations. Record actual test counts and scope in the dashboard.
This completes the first processor/protocol demonstration.

## Stage 6: Add input capture and scratch-bit operations

Extend specification, encoder, reference, core and HDL tests together:

| Instruction | Proposed behavior; one cycle each |
|---|---|
| `CAPTURE_INPUTS` | Copy eight sampled inputs into scratch bits 0..7; clear bits 8..63 |
| `EVAL_BIT` | Read two scratch bits, apply a four-entry truth table, write one bit |
| `WRITE_BIT` | Copy a scratch bit to one pin, preserving other outputs |

Reuse historical encodings unless a documented reason warrants changing them.
Read both EVAL_BIT operands before updating the destination, including aliases.

Dynamic indexing is absent from the current DSL. Start with bounded decoder
expansion for scratch selection/update. Measure graph and emitted HDL size;
functional success does not establish efficient multiplexers or physical timing.
Document synchronization and sampling latency at the input integration boundary.

**Exit evidence:** all truth tables and operand-bit combinations, address bounds
and aliases, all input bytes, pin preservation, malformed encodings and execution
sequences checked across reference, native, IR and HDL paths.

## Stage 7: Add runtime control flow and result handling

Input capture alone cannot implement reactive receivers. Specify conditional
branches, jumps and bounded runtime counters before implementing protocols that
need them. Define cycle costs, predicates, target validation and fault behavior.

Revisit image validation: loops invalidate the initial rule rejecting code after
an earlier HALT. Distinguish structural validity from termination; retain host
execution limits. Define how received data and protocol errors become observable.
Begin with single transfers; buffering is separate work.

Implement a polling example with a timeout and data-dependent branch. Count all
capture, computation and branch instructions in its timing.

**Exit evidence:** independent native/IR/clocked-HDL traces covering taken/untaken
branches, loop counts, target boundaries, timeout edges and changing inputs.

## Stage 8: Implement further protocols in dependency order

Each row is a separate milestone. Specify supported roles, modes, parameters and
timing first, using the applicable protocol specification. Add an independent
peer or waveform oracle, normal/error cases and native/IR/clocked-HDL comparisons.
Record unimplemented modes explicitly rather than claiming broad conformance.

| Order | Scope | Prerequisites and acceptance focus |
|---|---|---|
| 1 | UART 8N1 TX | Stage 5; exact periods and capacity boundaries |
| 2 | SPI controller | Input/scratch operations and a received-data interface; start with one mode and fixed-width transfers, then cover CPOL/CPHA modes, bit order, chip select and sampling schedules |
| 3 | UART 8N1 RX | Runtime branches, input-latency budget and result/error interface; start detection, sampling phase variation, back-to-back frames, bad stop bits and timeout |
| 4 | I²C controller | Branches/timeouts and drive-low/release controls; START/STOP, ACK/NACK, bus-idle checks and clock stretching; single-controller scope until arbitration is implemented |
| 5 | JTAG controller | Capture and state sequencing; TAP transitions, reset sequence, instruction/data shifting and captured results |
| 6 | SWD host | Bidirectional turnaround/pad controls; request/response, acknowledgments, parity, WAIT/FAULT handling and bounded retries |
| 7 | PS/2, selected role | Open-drain integration, input handling and timeouts; framing, parity, inhibit and role-specific behavior |
| 8 | CAN, USB, Ethernet feasibility | Separate studies selecting role/variant, external PHY/transceiver, clocking, throughput, buffering and required dedicated hardware before implementation |

Choose protocol rates only after an instruction schedule and synchronization
latency budget demonstrate feasibility. UART TX's one-clock bit support does not
imply the same rate for SPI or RX.

For bidirectional protocols, extend the interface with separate output-value and
output-enable ports. Verify release/drive sequencing with a resolved-bus testbench
and independent peer. Pull-ups, voltages, pad modes and signal integrity require
separate electrical integration evidence.

## Stage 9: Compose protocols and optionally add a Rust frontend

Extract common host builder operations: masked writes, cycle-aware delays,
sampling, branches, labels, capacity checks and listings. Compose two operations
on one sequential engine; verify pin ownership, entry/exit levels, results and
total timing. Shared pins require explicit handoff. Independent concurrent engines
require a separate resource/concurrency design.

Only then consider an annotated protocol frontend, separate from `#[logic]` and
optional for builder users. Distinguish host-specialized configuration from target
runtime values in its IR. Source control flow is runtime branching only when it
actually lowers to runtime instructions. Verify lowering and delay simplification
against independent waveforms and cycle traces.

**Exit evidence:** composed and frontend-generated programs meet independently
specified timing/behavior and reject capacity/resource errors.

## Stage 10: Select a physical target and measure it

Select FPGA or ASIC requirements, program storage, synchronizers, reset and pads.
Measure synthesis resources and critical paths, including decode/scratch selectors.
Synchronous instruction RAM or pipelining changes the cycle contract and requires
protocol regression; it is not a transparent memory substitution.

Track functional simulation, synthesis, placement/routing, timing, board behavior,
and electrical verification separately. ASIC DRC/LVS and signoff remain separate
work; no earlier milestone establishes them.

## Completion rules

Finish stages 1–5 before broadening protocol scope. Stages 6/7 gate the reactive
protocols that need them. The optional frontend must not delay the first demo.

For every material Rust change run:

```sh
cargo fmt --all
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
```

Install Icarus (`iverilog`, `vvp`), include example tests in the workspace suite,
preserve `Cargo.lock`, and exercise relevant demo/emission commands.

Update README's date, feature matrix, roadmap and limitations in the same change;
record exact evidence in `docs/verification.md`. Scope every completion claim to
the role/variant tested. Preserve unresolved limitations even when unrelated tests
pass. All ten stages now have scoped implementation/study evidence, including
complete back-to-back UART capture, IR/DR sequencing and the SKY130 HD block flow.
The optional frontend was considered and deferred. Full-chip integration,
multi-corner analysis, independent physical signoff and hardware validation remain
explicit future work; they are not implied by this example's completion. Existing
protocol limits remain documented rather than hidden by a broad completion label.
