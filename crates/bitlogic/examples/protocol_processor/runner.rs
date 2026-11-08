use super::{core::processor_step, isa::Program, reference::State};
use bitlogic::{Logic, bits};

pub fn native_step(state: State, instruction: u32, inputs: u8, reset: bool) -> State {
    if reset {
        return State::default();
    }
    let (mut pc, mut wait, mut pins) = (bits::<8>(0), bits::<16>(0), bits::<8>(0));
    let (mut halted, mut fault) = (false, false);
    let mut scratch = bits::<64>(0);
    let mut count = bits::<16>(0);
    let mut enables = bits::<8>(0);
    processor_step(
        &bits(state.pc.into()),
        &bits(state.wait.into()),
        &bits(state.pins.into()),
        &state.halted,
        &state.fault,
        &bits(state.scratch),
        &bits(state.count.into()),
        &bits(state.enables.into()),
        &bits(instruction.into()),
        &bits(inputs.into()),
        &mut pc,
        &mut wait,
        &mut pins,
        &mut halted,
        &mut fault,
        &mut scratch,
        &mut count,
        &mut enables,
    );
    State {
        pc: pc.get() as u8,
        wait: wait.get() as u16,
        pins: pins.get() as u8,
        halted,
        fault,
        scratch: scratch.get(),
        count: count.get() as u16,
        enables: enables.get() as u8,
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
