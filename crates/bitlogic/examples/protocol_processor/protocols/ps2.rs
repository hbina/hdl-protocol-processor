//! One device-to-host PS/2 byte. Host commands/retransmission are caller work.
use crate::{
    assembler::Assembler,
    isa::{Error, Instruction as I, Pin, Program, Register},
};

#[derive(Clone, Copy, Debug)]
pub struct Config {
    pub clock: Pin,
    pub data: Pin,
    pub hold: u16,
    pub idle_hold: u16,
    pub attempts: u16,
}

pub fn device_transmit(byte: u8, config: Config) -> Result<Program, Error> {
    if config.clock == config.data
        || config.hold == 0
        || config.idle_hold == 0
        || config.attempts == 0
    {
        return Err(Error(
            "PS/2 needs distinct pins and nonzero hold/idle/attempts".into(),
        ));
    }
    let clock = 1 << config.clock.index();
    let data = 1 << config.data.index();
    let bus = clock | data;
    let mut a = Assembler::default();
    for bit in 59..64 {
        a.set_bit(reg(bit), false);
    }
    drive(&mut a, bus, 0);
    a.emit(I::LoadCount(config.attempts));
    a.label("wait_idle")?;
    sample(&mut a, config.clock, 0);
    a.branch(reg(0), true, "idle");
    a.dec_jump("wait_idle");
    a.set_bit(reg(59), true);
    a.jump("abort");
    a.label("idle")?;
    sample(&mut a, config.data, 1);
    a.branch(reg(1), false, "request");
    a.delay(config.idle_hold);
    sample(&mut a, config.clock, 0);
    a.branch(reg(0), false, "inhibited");
    sample(&mut a, config.data, 1);
    a.branch(reg(1), false, "request");
    let mut symbols = vec![false];
    symbols.extend((0..8).map(|bit| byte & (1 << bit) != 0));
    symbols.push(byte.count_ones().is_multiple_of(2));
    symbols.push(true);
    for (index, high) in symbols.into_iter().enumerate() {
        drive(&mut a, data, if high { 0 } else { data });
        a.delay(config.hold);
        sample(&mut a, config.clock, 0);
        a.branch(reg(0), false, "inhibited");
        drive(&mut a, clock, clock); // Host samples the falling edge.
        a.delay(config.hold);
        drive(&mut a, clock, 0);
        if index != 10 {
            sample(&mut a, config.clock, 0);
            a.branch(reg(0), false, "inhibited");
        }
    }
    a.set_bit(reg(62), true);
    a.jump("release");
    a.label("inhibited")?;
    a.set_bit(reg(61), true);
    a.jump("abort");
    a.label("request")?;
    a.set_bit(reg(60), true);
    a.label("abort")?;
    a.set_bit(reg(63), true);
    a.label("release")?;
    drive(&mut a, bus, 0);
    a.emit(I::Halt);
    a.finish()
}

fn reg(index: u8) -> Register {
    Register::new(index).expect("constant scratch address")
}
fn sample(a: &mut Assembler, pin: Pin, index: u8) {
    a.emit(I::SampleBit {
        dst: reg(index),
        pin,
    });
}
fn drive(a: &mut Assembler, mask: u8, enables: u8) {
    a.emit(I::ConfigurePins {
        mask,
        enables,
        value: 0,
    });
}
