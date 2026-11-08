use std::{fmt, num::NonZeroU16};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Error(pub String);
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for Error {}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Pin(u8);
impl Pin {
    pub fn new(index: u8) -> Result<Self, Error> {
        if index < 8 {
            Ok(Self(index))
        } else {
            Err(Error("pin must be in 0..8".into()))
        }
    }
    pub fn index(self) -> u8 {
        self.0
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Register(u8);
impl Register {
    pub fn new(index: u8) -> Result<Self, Error> {
        if index < 64 {
            Ok(Self(index))
        } else {
            Err(Error("scratch register must be in 0..64".into()))
        }
    }
    pub fn index(self) -> u8 {
        self.0
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TruthTable(u8);
impl TruthTable {
    pub fn new(value: u8) -> Result<Self, Error> {
        if value < 16 {
            Ok(Self(value))
        } else {
            Err(Error("truth table must be in 0..16".into()))
        }
    }
    pub fn value(self) -> u8 {
        self.0
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Instruction {
    ParityWord(Register),
    SampleAndSet {
        dst: Register,
        pin: Pin,
        mask: u8,
        value: u8,
    },
    ConfigurePins {
        mask: u8,
        enables: u8,
        value: u8,
    },
    SetPins {
        mask: u8,
        value: u8,
    },
    Wait(NonZeroU16),
    CaptureInputs,
    EvalBit {
        dst: Register,
        lhs: Register,
        rhs: Register,
        table: TruthTable,
    },
    WriteBit {
        src: Register,
        pin: Pin,
    },
    Jump(u8),
    BranchBit {
        src: Register,
        value: bool,
        target: u8,
    },
    LoadCount(u16),
    DecJump(u8),
    SampleBit {
        dst: Register,
        pin: Pin,
    },
    Halt,
}

impl Instruction {
    pub fn encode(self) -> u32 {
        match self {
            Self::ParityWord(dst) => 0xd0000000 | (u32::from(dst.index()) << 16),
            Self::SampleAndSet {
                dst,
                pin,
                mask,
                value,
            } => {
                0xc0000000
                    | (u32::from(mask) << 17)
                    | (u32::from(value & mask) << 9)
                    | (u32::from(dst.index()) << 3)
                    | u32::from(pin.index())
            }
            Self::ConfigurePins {
                mask,
                enables,
                value,
            } => {
                0xb0000000
                    | (u32::from(mask) << 16)
                    | (u32::from(enables & mask) << 8)
                    | u32::from(value & mask)
            }
            Self::SetPins { mask, value } => {
                0x1000_0000 | (u32::from(mask) << 8) | u32::from(value & mask)
            }
            Self::Wait(cycles) => 0x2000_0000 | u32::from(cycles.get()),
            Self::CaptureInputs => 0x40000000,
            Self::EvalBit {
                dst,
                lhs,
                rhs,
                table,
            } => {
                0x30000000
                    | (u32::from(dst.index()) << 16)
                    | (u32::from(lhs.index()) << 10)
                    | (u32::from(rhs.index()) << 4)
                    | u32::from(table.value())
            }
            Self::WriteBit { src, pin } => {
                0x50000000 | (u32::from(src.index()) << 3) | u32::from(pin.index())
            }
            Self::Halt => 0xf000_0000,
            Self::Jump(target) => 0x60000000 | u32::from(target),
            Self::BranchBit { src, value, target } => {
                0x70000000
                    | (u32::from(value) << 14)
                    | (u32::from(src.index()) << 8)
                    | u32::from(target)
            }
            Self::LoadCount(count) => 0x80000000 | u32::from(count),
            Self::DecJump(target) => 0x90000000 | u32::from(target),
            Self::SampleBit { dst, pin } => {
                0xa0000000 | (u32::from(dst.index()) << 3) | u32::from(pin.index())
            }
        }
    }
    pub fn decode(word: u32) -> Result<Self, Error> {
        match word >> 28 {
            13 if word & 0x0fc0ffff == 0 => {
                Ok(Self::ParityWord(Register::new(((word >> 16) & 63) as u8)?))
            }
            12 if word & 0x0e000000 == 0 => Ok(Self::SampleAndSet {
                dst: Register::new(((word >> 3) & 63) as u8)?,
                pin: Pin::new((word & 7) as u8)?,
                mask: (word >> 17) as u8,
                value: (word >> 9) as u8,
            }),
            11 if word & 0x0f000000 == 0 => Ok(Self::ConfigurePins {
                mask: (word >> 16) as u8,
                enables: (word >> 8) as u8,
                value: word as u8,
            }),
            1 if word & 0x0fff_0000 == 0 => Ok(Self::SetPins {
                mask: (word >> 8) as u8,
                value: word as u8,
            }),
            2 if word & 0x0fff_0000 == 0 => NonZeroU16::new(word as u16)
                .map(Self::Wait)
                .ok_or_else(|| Error("WAIT(0) is invalid".into())),
            3 if word & 0x0fc00000 == 0 => Ok(Self::EvalBit {
                dst: Register::new(((word >> 16) & 63) as u8)?,
                lhs: Register::new(((word >> 10) & 63) as u8)?,
                rhs: Register::new(((word >> 4) & 63) as u8)?,
                table: TruthTable::new((word & 15) as u8)?,
            }),
            4 if word == 0x40000000 => Ok(Self::CaptureInputs),
            5 if word & 0x0ffffe00 == 0 => Ok(Self::WriteBit {
                src: Register::new(((word >> 3) & 63) as u8)?,
                pin: Pin::new((word & 7) as u8)?,
            }),
            15 if word == 0xf000_0000 => Ok(Self::Halt),
            6 if word & 0x0fffff00 == 0 => Ok(Self::Jump(word as u8)),
            7 if word & 0x0fff8000 == 0 => Ok(Self::BranchBit {
                src: Register::new(((word >> 8) & 63) as u8)?,
                value: word & 0x4000 != 0,
                target: word as u8,
            }),
            8 if word & 0x0fff0000 == 0 => Ok(Self::LoadCount(word as u16)),
            9 if word & 0x0fffff00 == 0 => Ok(Self::DecJump(word as u8)),
            10 if word & 0x0ffffe00 == 0 => Ok(Self::SampleBit {
                dst: Register::new(((word >> 3) & 63) as u8)?,
                pin: Pin::new((word & 7) as u8)?,
            }),
            _ => Err(Error(format!("invalid instruction {word:08x}"))),
        }
    }
}

#[derive(Clone, Debug)]
pub struct Program(Vec<Instruction>);
impl Program {
    pub fn new(instructions: Vec<Instruction>) -> Result<Self, Error> {
        if instructions.is_empty() || instructions.len() > 256 {
            return Err(Error("program must contain 1..=256 words".into()));
        }
        if instructions.last() != Some(&Instruction::Halt) {
            return Err(Error("program must end with HALT".into()));
        }
        for instruction in &instructions {
            let target = match instruction {
                Instruction::Jump(target)
                | Instruction::DecJump(target)
                | Instruction::BranchBit { target, .. } => Some(*target),
                _ => None,
            };
            if target.is_some_and(|target| usize::from(target) >= instructions.len()) {
                return Err(Error("branch target is outside the program image".into()));
            }
        }
        Ok(Self(instructions))
    }
    pub fn instructions(&self) -> &[Instruction] {
        &self.0
    }
    pub fn words(&self) -> Vec<u32> {
        self.instructions()
            .iter()
            .map(|instruction| instruction.encode())
            .collect()
    }
}
