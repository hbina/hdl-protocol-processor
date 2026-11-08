//! Reset TAP, scan one IR or DR register LSB first, return to Run-Test/Idle.
use crate::isa::{Error, Instruction as I, Pin, Program, Register};
use std::num::NonZeroU16;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RegisterKind {
    Instruction,
    Data,
}
#[derive(Clone, Copy, Debug)]
pub struct Config {
    pub tck: Pin,
    pub tms: Pin,
    pub tdi: Pin,
    pub tdo: Pin,
    pub hold: u16,
}

#[derive(Clone, Copy, Debug)]
pub struct Scan {
    pub kind: RegisterKind,
    pub value: u32,
    pub width: u8,
    pub capture: u8,
}

pub fn scan(kind: RegisterKind, value: u32, width: u8, config: Config) -> Result<Program, Error> {
    sequence(
        &[Scan {
            kind,
            value,
            width,
            capture: 0,
        }],
        config,
    )
}

pub fn sequence(scans: &[Scan], config: Config) -> Result<Program, Error> {
    let pins = [config.tck, config.tms, config.tdi, config.tdo];
    if pins
        .iter()
        .enumerate()
        .any(|(i, pin)| pins[..i].contains(pin))
        || config.hold == 0
    {
        return Err(Error(
            "JTAG needs four distinct pins and nonzero hold".into(),
        ));
    }
    if scans.is_empty() || scans.len() > 64 {
        return Err(Error("JTAG sequence needs 1..=64 scans".into()));
    }
    let mut captures = 0_u64;
    for scan in scans {
        if !(1..=32).contains(&scan.width)
            || (scan.width < 32 && scan.value >> scan.width != 0)
            || u16::from(scan.capture) + u16::from(scan.width) > 64
        {
            return Err(Error("JTAG width/value/capture range is invalid".into()));
        }
        let mask = ((1_u64 << scan.width) - 1) << scan.capture;
        if captures & mask != 0 {
            return Err(Error("JTAG capture ranges overlap".into()));
        }
        captures |= mask;
    }
    let outputs = (1 << config.tck.index()) | (1 << config.tms.index()) | (1 << config.tdi.index());
    let mut code = vec![I::ConfigurePins {
        mask: outputs | (1 << config.tdo.index()),
        enables: outputs,
        value: 0,
    }];
    for _ in 0..5 {
        pulse(&mut code, config, true, false, None)?;
    }
    pulse(&mut code, config, false, false, None)?; // Reset -> Idle.
    for scan in scans {
        pulse(&mut code, config, true, false, None)?; // Select-DR.
        if scan.kind == RegisterKind::Instruction {
            pulse(&mut code, config, true, false, None)?;
        }
        pulse(&mut code, config, false, false, None)?; // Capture.
        pulse(&mut code, config, false, false, None)?; // Shift.
        for bit in 0..scan.width {
            pulse(
                &mut code,
                config,
                bit + 1 == scan.width,
                scan.value & (1 << bit) != 0,
                Some(scan.capture + bit),
            )?;
        }
        pulse(&mut code, config, true, false, None)?; // Exit1 -> Update.
        pulse(&mut code, config, false, false, None)?; // Update -> Idle.
    }
    code.push(I::SetPins {
        mask: 1 << config.tck.index(),
        value: 0,
    });
    code.push(I::Halt);
    Program::new(code)
}

fn pulse(
    code: &mut Vec<I>,
    config: Config,
    tms: bool,
    tdi: bool,
    capture: Option<u8>,
) -> Result<(), Error> {
    let clock = 1 << config.tck.index();
    code.push(I::SetPins {
        mask: clock | (1 << config.tms.index()) | (1 << config.tdi.index()),
        value: if tms { 1 << config.tms.index() } else { 0 }
            | if tdi { 1 << config.tdi.index() } else { 0 },
    });
    code.push(I::Wait(NonZeroU16::new(config.hold).unwrap()));
    code.push(I::SetPins {
        mask: clock,
        value: clock,
    });
    if let Some(dst) = capture {
        code.push(I::SampleBit {
            dst: Register::new(dst)?,
            pin: config.tdo,
        });
    }
    code.push(I::Wait(NonZeroU16::new(config.hold).unwrap()));
    // The next pulse's setup also supplies the falling edge; one final falling
    // edge is emitted by sequence(). This preserves TMS/TDI setup before rising.
    Ok(())
}
