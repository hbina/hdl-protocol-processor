//! Clocked pin processor expressed in RHDL. Program memory is external.
//!
//! Width mismatches are rejected by Rust:
//! ```compile_fail
//! use rhdl::prelude::*;
//! let a: b8 = bits(1);
//! let b: b4 = bits(2);
//! let _ = a + b;
//! ```
use rhdl::prelude::*;
use rhdl_fpga::core::dff::DFF;

#[derive(Clone, Copy, Debug, Default, PartialEq, Digital)]
pub struct State {
    pub pc: b8,
    pub wait_remaining: b16,
    pub pins: b8,
    pub halted: bool,
    pub fault: bool,
}

#[kernel]
pub fn step(instruction: b32, state: State) -> State {
    let mut next = state;
    if state.halted {
        return next;
    }
    if state.wait_remaining != 0 {
        next.wait_remaining = state.wait_remaining - 1;
        return next;
    }
    let opcode = instruction >> 28;
    let payload = instruction & 0x0fff_ffff;
    let operand: b16 = instruction.resize();
    if opcode == 15 && payload == 0 {
        next.halted = true;
    } else if state.pc == 255 {
        next.halted = true;
        next.fault = true;
    } else if opcode == 1 && payload >> 16 == 0 {
        let mask: b8 = (instruction >> 8).resize();
        let value: b8 = instruction.resize();
        next.pins = (state.pins & !mask) | (value & mask);
        next.pc = state.pc + 1;
    } else if opcode == 2 && payload >> 16 == 0 && operand != 0 {
        next.wait_remaining = operand - 1;
        next.pc = state.pc + 1;
    } else {
        next.halted = true;
        next.fault = true;
    }
    next
}

#[derive(Clone, Default, Synchronous, SynchronousDQ)]
pub struct Processor {
    state: DFF<State>,
}

impl SynchronousIO for Processor {
    type I = b32;
    type O = State;
    type Kernel = processor;
}

#[kernel]
pub fn processor(_cr: ClockReset, instruction: b32, q: ProcessorQ) -> (State, ProcessorD) {
    (
        q.state,
        ProcessorD {
            state: step(instruction, q.state),
        },
    )
}

/// Export named ports around the RHDL synchronous circuit and register bank.
pub fn emit_verilog() -> Result<String, RHDLError> {
    let mut fixture = Fixture::new("protocol_processor", Adapter::<Processor, Red>::default());
    let (input, output) = fixture.io_dont_care();
    bind!(fixture, clk -> input.clock_reset.val().clock);
    bind!(fixture, reset -> input.clock_reset.val().reset);
    bind!(fixture, instruction -> input.input.val());
    bind!(fixture, pc <- output.val().pc);
    bind!(fixture, wait_remaining <- output.val().wait_remaining);
    bind!(fixture, pins <- output.val().pins);
    bind!(fixture, halted <- output.val().halted);
    bind!(fixture, fault <- output.val().fault);
    Ok(fixture.module()?.to_string())
}
