//! Shared instruction encoding and independent, cycle-level reference machine.
use std::{error::Error, fmt, num::NonZeroU16};

pub const PROGRAM_CAPACITY: usize = 256;
pub const PIN_COUNT: u8 = 8;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Pin(u8);

impl Pin {
    pub fn new(index: u8) -> Result<Self, ProgramError> {
        if index < PIN_COUNT {
            Ok(Self(index))
        } else {
            Err(ProgramError("pin index must be in 0..8"))
        }
    }

    pub fn mask(self) -> u8 {
        1 << self.0
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Instruction {
    SetPins { mask: u8, value: u8 },
    Wait(NonZeroU16),
    Halt,
}

impl Instruction {
    pub const fn encode(self) -> u32 {
        match self {
            Self::SetPins { mask, value } => {
                0x1000_0000 | ((mask as u32) << 8) | ((value & mask) as u32)
            }
            Self::Wait(cycles) => 0x2000_0000 | cycles.get() as u32,
            Self::Halt => 0xf000_0000,
        }
    }

    pub fn decode(word: u32) -> Result<Self, ProgramError> {
        match word >> 28 {
            1 if word & 0x0fff_0000 == 0 => Ok(Self::SetPins {
                mask: (word >> 8) as u8,
                value: word as u8,
            }),
            2 if word & 0x0fff_0000 == 0 => NonZeroU16::new(word as u16)
                .map(Self::Wait)
                .ok_or(ProgramError("WAIT requires at least one cycle")),
            15 if word & 0x0fff_ffff == 0 => Ok(Self::Halt),
            _ => Err(ProgramError("invalid opcode or reserved instruction bits")),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ProgramError(pub &'static str);

impl fmt::Display for ProgramError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.0)
    }
}

impl Error for ProgramError {}

#[derive(Clone, Debug)]
pub struct Program {
    instructions: Vec<Instruction>,
}

impl Program {
    pub fn new(instructions: Vec<Instruction>) -> Result<Self, ProgramError> {
        if instructions.is_empty() || instructions.len() > PROGRAM_CAPACITY {
            return Err(ProgramError("program must contain 1..=256 instructions"));
        }
        if instructions.last() != Some(&Instruction::Halt) {
            return Err(ProgramError("program must end in HALT"));
        }
        if instructions[..instructions.len() - 1].contains(&Instruction::Halt) {
            return Err(ProgramError("instructions after HALT are unreachable"));
        }
        Ok(Self { instructions })
    }

    pub fn instructions(&self) -> &[Instruction] {
        &self.instructions
    }

    pub fn words(&self) -> Vec<u32> {
        self.instructions.iter().map(|op| op.encode()).collect()
    }

    pub fn to_memh(&self) -> String {
        use fmt::Write;
        let mut text = String::new();
        for word in self.words() {
            writeln!(text, "{word:08x}").unwrap();
        }
        text
    }

    /// Human-readable listing of the final instruction image (not an assembler input).
    pub fn to_assembly(&self) -> String {
        use fmt::Write;
        let mut text = String::new();
        for (pc, instruction) in self.instructions.iter().enumerate() {
            write!(text, "{pc:03x}: ").unwrap();
            match instruction {
                Instruction::SetPins { mask, value } => {
                    writeln!(text, "SET_PINS 0x{mask:02x}, 0x{:02x}", value & mask).unwrap();
                }
                Instruction::Wait(cycles) => writeln!(text, "WAIT {}", cycles.get()).unwrap(),
                Instruction::Halt => writeln!(text, "HALT").unwrap(),
            }
        }
        text
    }
}

/// Each call models one rising edge, independently of the RHDL implementation.
#[derive(Default, Clone, Copy, Debug, PartialEq, Eq)]
pub struct Machine {
    pub pc: u8,
    pub wait_remaining: u16,
    pub pins: u8,
    pub halted: bool,
    pub fault: bool,
}

impl Machine {
    pub fn tick(&mut self, word: u32) {
        if self.halted {
            return;
        }
        if self.wait_remaining != 0 {
            self.wait_remaining -= 1;
            return;
        }
        let instruction = Instruction::decode(word);
        match instruction {
            Ok(Instruction::Halt) => self.halted = true,
            Ok(_) if self.pc == u8::MAX => self.fail(),
            Ok(Instruction::SetPins { mask, value }) => {
                self.pins = (self.pins & !mask) | (value & mask);
                self.pc += 1;
            }
            Ok(Instruction::Wait(cycles)) => {
                self.wait_remaining = cycles.get() - 1;
                self.pc += 1;
            }
            Err(_) => self.fail(),
        }
    }

    fn fail(&mut self) {
        self.halted = true;
        self.fault = true;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn encoding_and_validation() {
        for cycles in 1..=u16::MAX {
            let op = Instruction::Wait(NonZeroU16::new(cycles).unwrap());
            assert_eq!(Instruction::decode(op.encode()).unwrap(), op);
        }
        for mask in 0..=255_u8 {
            for value in 0..=255_u8 {
                let op = Instruction::SetPins { mask, value };
                assert_eq!(
                    Instruction::decode(op.encode()).unwrap(),
                    Instruction::SetPins {
                        mask,
                        value: value & mask
                    }
                );
            }
        }
        for word in [0, 0x2000_0000, 0x1001_0000, 0xf000_0001] {
            assert!(Instruction::decode(word).is_err());
        }
        assert!(Pin::new(8).is_err());
        assert!(Program::new(vec![]).is_err());
        assert!(Program::new(vec![Instruction::SetPins { mask: 1, value: 1 }]).is_err());
        assert!(Program::new(vec![Instruction::Halt; 2]).is_err());
        assert!(Program::new(vec![Instruction::Halt; 257]).is_err());
    }
}
