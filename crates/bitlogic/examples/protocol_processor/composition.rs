//! Sequential composition with explicit successful exits and shared-pin handoff.
use crate::isa::{Error, Instruction as I, Program};
use std::num::NonZeroU16;

pub struct Operation {
    name: String,
    program: Program,
    exits: Vec<u8>,
    pins: u8,
}
impl Operation {
    pub fn new(name: &str, program: Program, exits: Vec<u8>) -> Result<Self, Error> {
        if exits.is_empty() {
            return Err(Error("operation needs a successful HALT exit".into()));
        }
        for (n, &exit) in exits.iter().enumerate() {
            if exits[..n].contains(&exit)
                || program.instructions().get(usize::from(exit)) != Some(&I::Halt)
            {
                return Err(Error(
                    "successful exits must name distinct HALT instructions".into(),
                ));
            }
        }
        let mut pins = 0;
        for instruction in program.instructions() {
            pins |= match *instruction {
                I::ConfigurePins { mask, .. } | I::SetPins { mask, .. } => mask,
                I::SampleBit { pin, .. } | I::WriteBit { pin, .. } => 1 << pin.index(),
                I::SampleAndSet { pin, mask, .. } => mask | (1 << pin.index()),
                I::CaptureInputs => 255,
                _ => 0,
            };
        }
        Ok(Self {
            name: name.into(),
            program,
            exits,
            pins,
        })
    }
    pub fn single_exit(name: &str, program: Program) -> Result<Self, Error> {
        let exits = program
            .instructions()
            .iter()
            .enumerate()
            .filter_map(|(index, &instruction)| {
                if instruction == I::Halt {
                    Some(index as u8)
                } else {
                    None
                }
            })
            .collect::<Vec<_>>();
        if exits.len() != 1 {
            return Err(Error(
                "single-exit operation must have exactly one HALT".into(),
            ));
        }
        Self::new(name, program, exits)
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Handoff {
    pub release: u8,
    pub clocks: u16,
}
#[derive(Clone, Debug)]
pub struct Location {
    pub name: String,
    pub entry: u8,
}
pub struct Composition {
    pub program: Program,
    pub locations: Vec<Location>,
}
#[derive(Default)]
pub struct Composer {
    code: Vec<I>,
    exits: Vec<usize>,
    active_pins: u8,
    locations: Vec<Location>,
}
impl Composer {
    pub fn push(&mut self, operation: Operation, handoff: Option<Handoff>) -> Result<(), Error> {
        if self.code.is_empty() && handoff.is_some() {
            return Err(Error(
                "first operation has no prior pins to hand off".into(),
            ));
        }
        let shared = self.active_pins & operation.pins;
        let release = handoff.map(|h| h.release).unwrap_or(0);
        if shared & !release != 0 {
            return Err(Error("shared pins need an explicit release handoff".into()));
        }
        if release & !self.active_pins != 0 {
            return Err(Error(
                "handoff may release only previously claimed pins".into(),
            ));
        }
        // Work on a candidate so rejected appends leave the composer usable.
        let mut code = self.code.clone();
        let continuation = code.len();
        if let Some(handoff) = handoff {
            if handoff.release != 0 {
                code.push(I::ConfigurePins {
                    mask: handoff.release,
                    enables: 0,
                    value: 0,
                });
            }
            if let Some(clocks) = NonZeroU16::new(handoff.clocks) {
                code.push(I::Wait(clocks));
            }
        }
        let base = code.len();
        if base + operation.program.instructions().len() > 256 {
            return Err(Error("composed image exceeds 256 words".into()));
        }
        let relocate =
            |target: u8| u8::try_from(base + usize::from(target)).expect("capacity checked");
        for instruction in operation.program.instructions() {
            code.push(match *instruction {
                I::Jump(target) => I::Jump(relocate(target)),
                I::DecJump(target) => I::DecJump(relocate(target)),
                I::BranchBit { src, value, target } => I::BranchBit {
                    src,
                    value,
                    target: relocate(target),
                },
                other => other,
            });
        }
        for &exit in &self.exits {
            code[exit] = I::Jump(continuation as u8);
        }
        Program::new(code.clone())?;
        self.exits = operation
            .exits
            .into_iter()
            .map(|exit| base + usize::from(exit))
            .collect();
        self.locations.push(Location {
            name: operation.name,
            entry: base as u8,
        });
        self.active_pins = (self.active_pins & !release) | operation.pins;
        self.code = code;
        Ok(())
    }
    pub fn finish(self) -> Result<Composition, Error> {
        Ok(Composition {
            program: Program::new(self.code)?,
            locations: self.locations,
        })
    }
}
