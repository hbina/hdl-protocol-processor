//! One eight-bit full-duplex transfer; received byte is scratch bits 32..39.
use crate::isa::{Error, Instruction as I, Pin, Program, Register};
use std::num::NonZeroU16;

#[derive(Clone, Copy, Debug)]
pub struct Config {
    pub clock: Pin,
    pub mosi: Pin,
    pub miso: Pin,
    pub select: Pin,
    pub mode: u8,
    pub lsb_first: bool,
    pub half_period: u32,
}

pub fn transfer(byte: u8, config: Config) -> Result<Program, Error> {
    let pins = [config.clock, config.mosi, config.miso, config.select];
    if pins
        .iter()
        .enumerate()
        .any(|(i, pin)| pins[..i].contains(pin))
    {
        return Err(Error("SPI pins must be distinct".into()));
    }
    if config.mode > 3 || !(2..=65536).contains(&config.half_period) {
        return Err(Error(
            "SPI mode must be 0..=3; half-period must be 2..=65536".into(),
        ));
    }
    let cpol = config.mode & 2 != 0;
    let cpha = config.mode & 1 != 0;
    let clock = 1 << config.clock.index();
    let mosi = 1 << config.mosi.index();
    let select = 1 << config.select.index();
    let idle = if cpol { clock } else { 0 };
    let active = idle ^ clock;
    let bit_index = |n: u8| if config.lsb_first { n } else { 7 - n };
    let data = |n| {
        if byte & (1_u8 << bit_index(n)) != 0 {
            mosi
        } else {
            0
        }
    };
    let mut code = vec![I::ConfigurePins {
        mask: clock | mosi | select | (1 << config.miso.index()),
        enables: clock | mosi | select,
        value: idle | select,
    }];
    code.push(I::SetPins {
        mask: clock | mosi | select,
        value: idle | if cpha { 0 } else { data(0) },
    });
    delay(&mut code, config.half_period - 1);
    for n in 0..8 {
        code.push(I::SetPins {
            mask: clock | if cpha { mosi } else { 0 },
            value: active | if cpha { data(n) } else { 0 },
        });
        if !cpha {
            code.push(I::SampleBit {
                dst: Register::new(32 + bit_index(n))?,
                pin: config.miso,
            });
        }
        delay(&mut code, config.half_period - if cpha { 1 } else { 2 });
        code.push(I::SetPins {
            mask: clock | if cpha { 0 } else { mosi },
            value: idle | if !cpha && n < 7 { data(n + 1) } else { 0 },
        });
        if cpha {
            code.push(I::SampleBit {
                dst: Register::new(32 + bit_index(n))?,
                pin: config.miso,
            });
        }
        delay(&mut code, config.half_period - if cpha { 2 } else { 1 });
    }
    code.push(I::SetPins {
        mask: select,
        value: select,
    });
    code.push(I::Halt);
    Program::new(code)
}

fn delay(code: &mut Vec<I>, clocks: u32) {
    if let Some(clocks) = NonZeroU16::new(clocks as u16) {
        code.push(I::Wait(clocks));
    }
}
