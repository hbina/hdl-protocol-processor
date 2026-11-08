//! Poll one synchronized input; scratch bit 62 reports success, bit 63 timeout.
use crate::isa::{Error, Instruction as I, Pin, Program, Register, TruthTable};
use std::num::NonZeroU16;

pub fn input_high(pin: Pin, attempts: u16, gap: u16) -> Result<Program, Error> {
    if attempts == 0 || gap == 0 {
        return Err(Error("poll attempts and gap must be nonzero".into()));
    }
    let zero = Register::new(0)?;
    Program::new(vec![
        I::LoadCount(attempts),
        I::CaptureInputs,
        I::BranchBit {
            src: Register::new(pin.index())?,
            value: true,
            target: 7,
        },
        I::Wait(NonZeroU16::new(gap).unwrap()),
        I::DecJump(1),
        I::EvalBit {
            dst: Register::new(63)?,
            lhs: zero,
            rhs: zero,
            table: TruthTable::new(15)?,
        },
        I::Halt,
        I::EvalBit {
            dst: Register::new(62)?,
            lhs: zero,
            rhs: zero,
            table: TruthTable::new(15)?,
        },
        I::Halt,
    ])
}
