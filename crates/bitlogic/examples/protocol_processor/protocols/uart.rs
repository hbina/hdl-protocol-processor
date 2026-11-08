use crate::{
    assembler::Assembler,
    isa::{Error, Instruction, Pin, Program, Register},
};
use std::num::NonZeroU16;

pub fn transmit(bytes: &[u8], pin: Pin, period: u32) -> Result<Program, Error> {
    if !(1..=65536).contains(&period) {
        return Err(Error("UART period must be 1..=65536 clocks".into()));
    }
    let words_per_interval = if period == 1 { 1 } else { 2 };
    let max_bytes = ((255 / words_per_interval) - 1) / 10;
    if bytes.len() > max_bytes {
        return Err(Error("UART image exceeds 256 words".into()));
    }
    let mut code = Vec::new();
    let mut interval = |high: bool| {
        let mask = 1 << pin.index();
        code.push(if code.is_empty() {
            Instruction::ConfigurePins {
                mask,
                enables: mask,
                value: if high { mask } else { 0 },
            }
        } else {
            Instruction::SetPins {
                mask,
                value: if high { mask } else { 0 },
            }
        });
        if let Some(wait) = NonZeroU16::new((period - 1) as u16) {
            code.push(Instruction::Wait(wait));
        }
    };
    interval(true);
    for &byte in bytes {
        interval(false);
        for bit in 0..8 {
            interval(byte & (1 << bit) != 0);
        }
        interval(true);
    }
    code.push(Instruction::Halt);
    Program::new(code)
}

/// One 8N1 frame. Scratch 32..39 is data, 62 success, 63 error,
/// 61 start timeout, 60 false start. Call after reset or clear these status bits.
pub fn receive(pin: Pin, period: u32, attempts: u16) -> Result<Program, Error> {
    receive_at(pin, period, attempts, 1, 32)
}

/// Receive 1..=6 adjacent frames, storing bytes in scratch 8..55.
pub fn receive_frames(pin: Pin, period: u32, attempts: u16, count: u8) -> Result<Program, Error> {
    if !(1..=6).contains(&count) {
        return Err(Error("UART RX batch must contain 1..=6 frames".into()));
    }
    receive_at(pin, period, attempts, count, 8)
}

fn receive_at(pin: Pin, period: u32, attempts: u16, count: u8, base: u8) -> Result<Program, Error> {
    use Instruction as I;
    if !(8..=65536).contains(&period) || !period.is_multiple_of(2) || attempts == 0 {
        return Err(Error(
            "UART RX needs an even period in 8..=65536 and nonzero attempts".into(),
        ));
    }
    let sample = |dst| {
        Ok(I::SampleBit {
            dst: Register::new(dst)?,
            pin,
        })
    };
    let reg = |index| Register::new(index).expect("constant scratch address");
    let mut a = Assembler::default();
    for frame in 0..count {
        let poll = a.fresh();
        let detected = a.fresh();
        a.emit(I::LoadCount(attempts));
        a.label(&poll)?;
        a.emit(sample(0)?);
        a.branch(reg(0), false, &detected);
        a.dec_jump(&poll);
        a.set_bit(reg(61), true);
        a.jump("error");
        a.label(&detected)?;
        a.delay((period / 2 - 2) as u16);
        a.emit(sample(0)?);
        a.branch(reg(0), true, "false_start");
        a.delay((period - 2) as u16);
        for bit in 0..8 {
            a.emit(sample(base + frame * 8 + bit)?);
            a.delay((period - 1) as u16);
        }
        a.emit(sample(0)?);
        a.branch(reg(0), false, "error");
    }
    a.set_bit(reg(62), true);
    a.emit(I::Halt);
    a.label("false_start")?;
    a.set_bit(reg(60), true);
    a.jump("error");
    a.label("error")?;
    a.set_bit(reg(63), true);
    a.emit(I::Halt);
    a.finish()
}
