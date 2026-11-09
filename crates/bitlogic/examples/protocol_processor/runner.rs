use super::{
    core::{ProcessorState, StepInput, processor_step},
    isa::Program,
    reference::State,
};
use bitlogic::{Logic, bits};

pub fn native_step(state: State, instruction: u32, inputs: u8, reset: bool) -> State {
    if reset {
        return State::default();
    }
    let next = processor_step(StepInput {
        state: ProcessorState {
            pc: bits(state.pc.into()),
            wait: bits(state.wait.into()),
            pins: bits(state.pins.into()),
            halted: state.halted,
            fault: state.fault,
            scratch: bits(state.scratch),
            count: bits(state.count.into()),
            enables: bits(state.enables.into()),
        },
        instruction: bits(instruction.into()),
        inputs: bits(inputs.into()),
    });
    State {
        pc: next.pc.get() as u8,
        wait: next.wait.get() as u16,
        pins: next.pins.get() as u8,
        halted: next.halted,
        fault: next.fault,
        scratch: next.scratch.get(),
        count: next.count.get() as u16,
        enables: next.enables.get() as u8,
    }
}

pub fn ir_step(ir: &Logic, state: State, word: u32, inputs: u8, reset: bool) -> State {
    if reset {
        return State::default();
    }
    let mut ports = state.values().to_vec();
    ports.extend([u64::from(word), u64::from(inputs)]);
    let next = ir.evaluate(&ports).expect("valid processor port widths");
    State {
        pc: next[0] as u8,
        wait: next[1] as u16,
        pins: next[2] as u8,
        halted: next[3] != 0,
        fault: next[4] != 0,
        scratch: next[5],
        count: next[6] as u16,
        enables: next[7] as u8,
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Outcome {
    Halted,
    Fault,
    Limit,
}

pub fn run(program: &Program, limit: usize) -> (Outcome, Vec<State>) {
    let words = program.words();
    let mut state = State::default();
    let mut trace = Vec::new();
    for _ in 0..limit {
        let word = words.get(usize::from(state.pc)).copied().unwrap_or(0);
        state = native_step(state, word, 0, false);
        trace.push(state);
        if state.halted {
            return (
                if state.fault {
                    Outcome::Fault
                } else {
                    Outcome::Halted
                },
                trace,
            );
        }
    }
    (Outcome::Limit, trace)
}
