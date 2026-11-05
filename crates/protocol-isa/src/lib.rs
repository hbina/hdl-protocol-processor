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
    SetPins {
        mask: u8,
        value: u8,
    },
    Wait(NonZeroU16),
    /// Bit addresses are checked by Program::new (0..64); table is four bits.
    EvalBit {
        dst: u8,
        lhs: u8,
        rhs: u8,
        table: u8,
    },
    CaptureInputs,
    WriteBit {
        src: u8,
        pin: u8,
    },
    Halt,
}

impl Instruction {
    pub const fn encode(self) -> u32 {
        match self {
            Self::SetPins { mask, value } => {
                0x1000_0000 | ((mask as u32) << 8) | ((value & mask) as u32)
            }
            Self::Wait(cycles) => 0x2000_0000 | cycles.get() as u32,
            Self::EvalBit {
                dst,
                lhs,
                rhs,
                table,
            } => {
                0x3000_0000
                    | ((dst as u32) << 16)
                    | ((lhs as u32) << 10)
                    | ((rhs as u32) << 4)
                    | table as u32
            }
            Self::CaptureInputs => 0x4000_0000,
            Self::WriteBit { src, pin } => 0x5000_0000 | ((src as u32) << 3) | pin as u32,
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
            3 if word & 0x0fc0_0000 == 0 => Ok(Self::EvalBit {
                dst: ((word >> 16) & 63) as u8,
                lhs: ((word >> 10) & 63) as u8,
                rhs: ((word >> 4) & 63) as u8,
                table: (word & 15) as u8,
            }),
            4 if word & 0x0fff_ffff == 0 => Ok(Self::CaptureInputs),
            5 if word & 0x0fff_fe00 == 0 => Ok(Self::WriteBit {
                src: ((word >> 3) & 63) as u8,
                pin: (word & 7) as u8,
            }),
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
        for instruction in &instructions {
            if matches!(instruction, Instruction::EvalBit {dst,lhs,rhs,table} if *dst>=64 || *lhs>=64 || *rhs>=64 || *table>=16)
                || matches!(instruction, Instruction::WriteBit {src,pin} if *src>=64 || *pin>=8)
            {
                return Err(ProgramError(
                    "bit register, truth table, or output pin out of range",
                ));
            }
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
                Instruction::EvalBit {
                    dst,
                    lhs,
                    rhs,
                    table,
                } => writeln!(text, "EVAL_BIT r{dst}, r{lhs}, r{rhs}, 0x{table:x}").unwrap(),
                Instruction::CaptureInputs => writeln!(text, "CAPTURE_INPUTS").unwrap(),
                Instruction::WriteBit { src, pin } => {
                    writeln!(text, "WRITE_BIT r{src}, pin{pin}").unwrap()
                }
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
    pub scratch: u64,
}

impl Machine {
    pub fn tick(&mut self, word: u32) {
        self.tick_with_inputs(word, 0);
    }

    pub fn tick_with_inputs(&mut self, word: u32, inputs: u8) {
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
            Ok(Instruction::CaptureInputs) => {
                self.scratch = u64::from(inputs);
                self.pc += 1;
            }
            Ok(Instruction::EvalBit {
                dst,
                lhs,
                rhs,
                table,
            }) => {
                let index = (((self.scratch >> lhs) & 1) << 1) | ((self.scratch >> rhs) & 1);
                let bit = u64::from((table >> index) & 1);
                self.scratch = (self.scratch & !(1_u64 << dst)) | (bit << dst);
                self.pc += 1;
            }
            Ok(Instruction::WriteBit { src, pin }) => {
                let value = (((self.scratch >> src) & 1) as u8) << pin;
                self.pins = (self.pins & !(1 << pin)) | value;
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

    #[test]
    fn bit_instruction_encoding_and_faults() {
        for dst in [0, 1, 63] {
            for lhs in [0, 1, 63] {
                for rhs in [0, 1, 63] {
                    for table in 0..16 {
                        let instruction = Instruction::EvalBit {
                            dst,
                            lhs,
                            rhs,
                            table,
                        };
                        assert_eq!(
                            Instruction::decode(instruction.encode()).unwrap(),
                            instruction
                        );
                    }
                }
            }
        }
        for src in 0..64 {
            for pin in 0..8 {
                let instruction = Instruction::WriteBit { src, pin };
                assert_eq!(
                    Instruction::decode(instruction.encode()).unwrap(),
                    instruction
                );
            }
        }
        assert_eq!(Instruction::CaptureInputs.encode(), 0x4000_0000);
        for invalid in [0x3040_0000, 0x3fff_ffff, 0x4000_0001, 0x5000_0200] {
            assert!(Instruction::decode(invalid).is_err());
            let mut m = Machine::default();
            m.tick_with_inputs(invalid, 255);
            assert!(m.halted && m.fault);
            assert_eq!(m.scratch, 0);
        }
        for invalid in [
            Instruction::EvalBit {
                dst: 64,
                lhs: 0,
                rhs: 0,
                table: 0,
            },
            Instruction::EvalBit {
                dst: 0,
                lhs: 64,
                rhs: 0,
                table: 0,
            },
            Instruction::EvalBit {
                dst: 0,
                lhs: 0,
                rhs: 64,
                table: 0,
            },
            Instruction::EvalBit {
                dst: 0,
                lhs: 0,
                rhs: 0,
                table: 16,
            },
            Instruction::WriteBit { src: 64, pin: 0 },
            Instruction::WriteBit { src: 0, pin: 8 },
        ] {
            assert!(Program::new(vec![invalid, Instruction::Halt]).is_err());
        }
    }
}
