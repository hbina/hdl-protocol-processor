//! SWD transfer layer: target already in SWD, one turnaround, no WAIT/FAULT data.
use crate::{
    assembler::Assembler,
    isa::{Error, Instruction as I, Pin, Program, Register, TruthTable},
};

#[derive(Clone, Copy, Debug)]
pub struct Config {
    pub clock: Pin,
    pub data: Pin,
    pub hold: u16,
    pub attempts: u16,
    pub retry_gap: u16,
}
#[derive(Clone, Copy, Debug)]
pub enum Transfer {
    Read,
    Write(u32),
}

pub fn transaction(
    ap: bool,
    address: u8,
    transfer: Transfer,
    cfg: Config,
) -> Result<Program, Error> {
    validate(cfg)?;
    if address > 12 || !address.is_multiple_of(4) {
        return Err(Error("SWD register address must be 0, 4, 8, or 12".into()));
    }
    let read = matches!(transfer, Transfer::Read);
    let fields = u8::from(ap) | (u8::from(read) << 1) | address;
    let request =
        1 | (fields << 1) | (u8::from(!fields.count_ones().is_multiple_of(2)) << 5) | 0x80;
    let mut a = Assembler::default();
    for bit in 8..14 {
        a.set_bit(reg(bit), false);
    }
    a.emit(I::LoadCount(cfg.attempts));
    a.label("request")?;
    configure(&mut a, cfg, true, true);
    for bit in 0..8 {
        transmit(&mut a, cfg, request & (1 << bit) != 0);
    }
    configure(&mut a, cfg, false, false);
    clock(&mut a, cfg); // Host-to-target turnaround.
    for bit in 0..3 {
        receive(&mut a, cfg, bit);
    }
    a.branch(reg(2), true, "ack_high");
    a.branch(reg(1), true, "ack_wait");
    a.branch(reg(0), false, "invalid");
    match transfer {
        Transfer::Read => {
            for bit in 0..32 {
                receive(&mut a, cfg, 32 + bit);
            }
            a.emit(I::ParityWord(reg(3)));
            receive(&mut a, cfg, 4);
            return_to_host(&mut a, cfg);
            a.emit(I::EvalBit {
                dst: reg(5),
                lhs: reg(3),
                rhs: reg(4),
                table: TruthTable::new(6).unwrap(),
            });
            a.branch(reg(5), true, "parity_error");
        }
        Transfer::Write(value) => {
            return_to_host(&mut a, cfg);
            for bit in 0..32 {
                transmit(&mut a, cfg, value & (1 << bit) != 0);
            }
            transmit(&mut a, cfg, value.count_ones() % 2 != 0);
        }
    }
    a.set_bit(reg(8), true);
    a.jump("finish");
    a.label("ack_high")?;
    a.branch(reg(0), true, "invalid");
    a.branch(reg(1), true, "invalid");
    a.set_bit(reg(11), true);
    a.jump("non_ok");
    a.label("ack_wait")?;
    a.branch(reg(0), true, "invalid");
    a.label("non_ok")?;
    return_to_host(&mut a, cfg);
    a.branch(reg(11), true, "error");
    a.delay(cfg.retry_gap);
    a.dec_jump("request");
    a.set_bit(reg(10), true);
    a.jump("error");
    a.label("invalid")?;
    a.set_bit(reg(13), true);
    // Unknown ACK: stay released for a full possible data phase before handoff.
    a.emit(I::LoadCount(33));
    a.label("backoff")?;
    clock(&mut a, cfg);
    a.dec_jump("backoff");
    return_to_host(&mut a, cfg);
    a.jump("error");
    a.label("parity_error")?;
    a.set_bit(reg(12), true);
    a.label("error")?;
    a.set_bit(reg(9), true);
    a.label("finish")?;
    // End with one low-data idle clock, then park high with clock low.
    configure(&mut a, cfg, true, false);
    clock(&mut a, cfg);
    configure(&mut a, cfg, true, true);
    a.emit(I::Halt);
    a.finish()
}

pub fn line_reset(cfg: Config) -> Result<Program, Error> {
    validate(cfg)?;
    let mut a = Assembler::default();
    configure(&mut a, cfg, true, true);
    a.emit(I::LoadCount(56));
    a.label("ones")?;
    clock(&mut a, cfg);
    a.dec_jump("ones");
    configure(&mut a, cfg, true, false);
    clock(&mut a, cfg);
    clock(&mut a, cfg);
    configure(&mut a, cfg, true, true);
    a.emit(I::Halt);
    a.finish()
}
fn validate(cfg: Config) -> Result<(), Error> {
    if cfg.clock == cfg.data || cfg.hold == 0 || cfg.attempts == 0 {
        return Err(Error(
            "SWD needs distinct pins and nonzero hold/attempts".into(),
        ));
    }
    Ok(())
}
fn reg(index: u8) -> Register {
    Register::new(index).expect("constant scratch address")
}
fn configure(a: &mut Assembler, cfg: Config, output: bool, high: bool) {
    let clock = 1 << cfg.clock.index();
    let data = 1 << cfg.data.index();
    a.emit(I::ConfigurePins {
        mask: clock | data,
        enables: clock | if output { data } else { 0 },
        value: if high { data } else { 0 },
    });
}
fn clock(a: &mut Assembler, cfg: Config) {
    let mask = 1 << cfg.clock.index();
    a.emit(I::SetPins { mask, value: 0 });
    a.delay(cfg.hold);
    a.emit(I::SetPins { mask, value: mask });
    a.delay(cfg.hold);
}
fn transmit(a: &mut Assembler, cfg: Config, high: bool) {
    let clock = 1 << cfg.clock.index();
    let data = 1 << cfg.data.index();
    a.emit(I::SetPins {
        mask: clock | data,
        value: if high { data } else { 0 },
    });
    a.delay(cfg.hold);
    a.emit(I::SetPins {
        mask: clock,
        value: clock,
    });
    a.delay(cfg.hold);
}
fn receive(a: &mut Assembler, cfg: Config, dst: u8) {
    let clock = 1 << cfg.clock.index();
    a.emit(I::SetPins {
        mask: clock,
        value: 0,
    });
    a.delay(cfg.hold);
    a.emit(I::SampleAndSet {
        dst: reg(dst),
        pin: cfg.data,
        mask: clock,
        value: clock,
    });
    a.delay(cfg.hold);
}
fn return_to_host(a: &mut Assembler, cfg: Config) {
    clock(a, cfg);
    a.emit(I::SetPins {
        mask: 1 << cfg.clock.index(),
        value: 0,
    });
    configure(a, cfg, true, true);
}
