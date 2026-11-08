//! Checked host assembly: labels are relocated before Program validation.
use crate::isa::{Error, Instruction as I, Program, Register, TruthTable};
use std::{collections::BTreeMap, num::NonZeroU16};

#[derive(Default)]
pub struct Assembler {
    code: Vec<I>,
    labels: BTreeMap<String, usize>,
    fixups: Vec<(usize, String)>,
    serial: usize,
}
impl Assembler {
    pub fn emit(&mut self, instruction: I) {
        self.code.push(instruction);
    }
    pub fn label(&mut self, name: &str) -> Result<(), Error> {
        if self.labels.contains_key(name) {
            return Err(Error(format!("duplicate label {name}")));
        }
        self.labels.insert(name.into(), self.code.len());
        Ok(())
    }
    pub fn fresh(&mut self) -> String {
        let label = format!("__local_{}", self.serial);
        self.serial += 1;
        label
    }
    fn relocate(&mut self, instruction: I, label: &str) {
        self.fixups.push((self.code.len(), label.into()));
        self.emit(instruction);
    }
    pub fn jump(&mut self, label: &str) {
        self.relocate(I::Jump(0), label);
    }
    pub fn branch(&mut self, src: Register, value: bool, label: &str) {
        self.relocate(
            I::BranchBit {
                src,
                value,
                target: 0,
            },
            label,
        );
    }
    pub fn dec_jump(&mut self, label: &str) {
        self.relocate(I::DecJump(0), label);
    }
    pub fn delay(&mut self, clocks: u16) {
        if let Some(clocks) = NonZeroU16::new(clocks) {
            self.emit(I::Wait(clocks));
        }
    }
    pub fn set_bit(&mut self, dst: Register, value: bool) {
        self.emit(I::EvalBit {
            dst,
            lhs: dst,
            rhs: dst,
            table: TruthTable::new(if value { 15 } else { 0 }).unwrap(),
        });
    }
    pub fn finish(mut self) -> Result<Program, Error> {
        if self.code.len() > 256 {
            return Err(Error(format!(
                "assembled image has {} words; maximum is 256",
                self.code.len()
            )));
        }
        for (index, label) in self.fixups {
            let target = *self
                .labels
                .get(&label)
                .ok_or_else(|| Error(format!("unbound label {label}")))?;
            let target =
                u8::try_from(target).map_err(|_| Error("label exceeds address space".into()))?;
            self.code[index] = match self.code[index] {
                I::Jump(_) => I::Jump(target),
                I::DecJump(_) => I::DecJump(target),
                I::BranchBit { src, value, .. } => I::BranchBit { src, value, target },
                _ => unreachable!("only branches have fixups"),
            };
        }
        Program::new(self.code)
    }
}
