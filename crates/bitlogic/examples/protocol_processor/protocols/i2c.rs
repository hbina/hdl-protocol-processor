//! Single-controller seven-bit I2C, one data byte per transaction.
use crate::{
    assembler::Assembler,
    isa::{Error, Instruction as I, Pin, Program, Register},
};

#[derive(Clone, Copy, Debug)]
pub struct Config {
    pub scl: Pin,
    pub sda: Pin,
    /// Additional hold clocks, not a requested bus frequency.
    pub hold: u16,
    /// Samples allowed each time SCL is released.
    pub stretch_attempts: u16,
}

#[derive(Clone, Copy, Debug)]
pub enum Transfer {
    Write(u8),
    Read,
}

pub fn transaction(address: u8, transfer: Transfer, config: Config) -> Result<Program, Error> {
    if !(0x08..=0x77).contains(&address) {
        return Err(Error(
            "I2C address must be an ordinary seven-bit address 0x08..=0x77".into(),
        ));
    }
    if config.scl == config.sda || config.hold == 0 || config.stretch_attempts == 0 {
        return Err(Error(
            "I2C needs distinct pins and nonzero hold/stretch attempts".into(),
        ));
    }
    let scl = 1 << config.scl.index();
    let sda = 1 << config.sda.index();
    let bus = scl | sda;
    let mut a = Assembler::default();
    for bit in 59..64 {
        a.set_bit(reg(bit), false);
    }
    drive(&mut a, bus, 0);
    sample(&mut a, config.scl, 0);
    a.branch(reg(0), false, "busy");
    sample(&mut a, config.sda, 1);
    a.branch(reg(1), false, "busy");
    a.delay(config.hold);
    drive(&mut a, sda, sda); // START: SDA falls while SCL is high.
    a.delay(config.hold);
    let read = matches!(transfer, Transfer::Read);
    for bit in (0..8).rev() {
        phase(
            &mut a,
            config,
            ((address << 1) | u8::from(read)) & (1 << bit) != 0,
            None,
        )?;
    }
    phase(&mut a, config, true, Some(1))?;
    a.branch(reg(1), true, "nack");
    match transfer {
        Transfer::Write(value) => {
            for bit in (0..8).rev() {
                phase(&mut a, config, value & (1 << bit) != 0, None)?;
            }
            phase(&mut a, config, true, Some(1))?;
            a.branch(reg(1), true, "nack");
        }
        Transfer::Read => {
            for bit in (0..8).rev() {
                phase(&mut a, config, true, Some(32 + bit))?;
            }
            phase(&mut a, config, true, None)?; // Controller NACK after the final byte.
        }
    }
    a.label("stop")?;
    drive(&mut a, bus, bus);
    a.delay(config.hold);
    drive(&mut a, scl, 0);
    await_clock(&mut a, config)?;
    a.delay(config.hold);
    drive(&mut a, sda, 0); // STOP: release SDA while observed SCL is high.
    a.delay(config.hold);
    a.branch(reg(63), true, "done");
    a.set_bit(reg(62), true);
    a.label("done")?;
    a.emit(I::Halt);
    a.label("nack")?;
    a.set_bit(reg(61), true);
    a.set_bit(reg(63), true);
    a.jump("stop");
    a.label("busy")?;
    a.set_bit(reg(60), true);
    a.jump("abort");
    a.label("timeout")?;
    a.set_bit(reg(59), true);
    a.label("abort")?;
    a.set_bit(reg(63), true);
    drive(&mut a, bus, 0); // Release even when a peer prevents STOP.
    a.emit(I::Halt);
    a.finish()
}

fn reg(index: u8) -> Register {
    Register::new(index).expect("constant scratch address")
}
fn drive(a: &mut Assembler, mask: u8, enables: u8) {
    a.emit(I::ConfigurePins {
        mask,
        enables,
        value: 0,
    });
}
fn sample(a: &mut Assembler, pin: Pin, dst: u8) {
    a.emit(I::SampleBit { dst: reg(dst), pin });
}
fn await_clock(a: &mut Assembler, config: Config) -> Result<(), Error> {
    let again = a.fresh();
    let high = a.fresh();
    a.emit(I::LoadCount(config.stretch_attempts));
    a.label(&again)?;
    sample(a, config.scl, 0);
    a.branch(reg(0), true, &high);
    a.dec_jump(&again);
    a.jump("timeout");
    a.label(&high)
}
fn phase(a: &mut Assembler, config: Config, high: bool, dst: Option<u8>) -> Result<(), Error> {
    let scl = 1 << config.scl.index();
    let sda = 1 << config.sda.index();
    drive(a, scl | sda, scl | if high { 0 } else { sda });
    a.delay(config.hold);
    drive(a, scl, 0);
    await_clock(a, config)?;
    if let Some(dst) = dst {
        sample(a, config.sda, dst);
    }
    a.delay(config.hold);
    drive(a, scl, scl);
    Ok(())
}
