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
    pub scratch: b64,
}

#[kernel]
pub fn step(instruction: b32, state: State) -> State {
    step_with_inputs(instruction, bits(0), state)
}

#[kernel]
pub fn step_with_inputs(instruction: b32, inputs: b8, state: State) -> State {
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
    } else if opcode == 3 && payload >> 22 == 0 {
        let dst: b6 = (instruction >> 16).resize();
        let lhs: b6 = (instruction >> 10).resize();
        let rhs: b6 = (instruction >> 4).resize();
        let table: b4 = instruction.resize();
        let a: b2 = ((state.scratch >> lhs) & 1).resize();
        let b: b2 = ((state.scratch >> rhs) & 1).resize();
        let index = (a << 1) | b;
        let value: b64 = ((table >> index) & 1).resize();
        let one: b64 = bits(1);
        next.scratch = (state.scratch & !(one << dst)) | (value << dst);
        next.pc = state.pc + 1;
    } else if opcode == 4 && payload == 0 {
        next.scratch = inputs.resize();
        next.pc = state.pc + 1;
    } else if opcode == 5 && payload >> 9 == 0 {
        let src: b6 = (instruction >> 3).resize();
        let pin: b3 = instruction.resize();
        let value: b8 = ((state.scratch >> src) & 1).resize();
        let one: b8 = bits(1);
        next.pins = (state.pins & !(one << pin)) | (value << pin);
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
    type I = ProcessorInput;
    type O = State;
    type Kernel = processor;
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Digital)]
pub struct ProcessorInput {
    pub instruction: b32,
    pub pins: b8,
}

#[kernel]
pub fn processor(_cr: ClockReset, input: ProcessorInput, q: ProcessorQ) -> (State, ProcessorD) {
    (
        q.state,
        ProcessorD {
            state: step_with_inputs(input.instruction, input.pins, q.state),
        },
    )
}

/// Export named ports around the RHDL synchronous circuit and register bank.
pub fn emit_verilog() -> Result<String, RHDLError> {
    let mut fixture = Fixture::new("protocol_processor", Adapter::<Processor, Red>::default());
    let (input, output) = fixture.io_dont_care();
    bind!(fixture, clk -> input.clock_reset.val().clock);
    bind!(fixture, reset -> input.clock_reset.val().reset);
    bind!(fixture, instruction -> input.input.val().instruction);
    bind!(fixture, inputs -> input.input.val().pins);
    bind!(fixture, pc <- output.val().pc);
    bind!(fixture, wait_remaining <- output.val().wait_remaining);
    bind!(fixture, pins <- output.val().pins);
    bind!(fixture, halted <- output.val().halted);
    bind!(fixture, fault <- output.val().fault);
    Ok(fixture.module()?.to_string())
}
