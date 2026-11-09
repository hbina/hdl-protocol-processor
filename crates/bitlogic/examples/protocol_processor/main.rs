mod assembler;
mod composition;
mod core;
mod isa;
mod protocols;
mod reference;
mod runner;
#[cfg(test)]
mod tests;

use isa::Pin;
use protocols::uart;

const USAGE: &str = "usage: protocol_processor MODE [ARGS]
  demo|mem|asm [TEXT [PIN [PERIOD]]]  UART transmit (defaults: Hi, 0, 8)
  poll [PIN [ATTEMPTS [GAP]]]        input polling (0, 4, 2)
  spi [HEX_BYTE [MODE [HALF_PERIOD]]] (a5, 0, 4)
  uart-rx [PIN [PERIOD [ATTEMPTS]]]  (0, 16, 8)
  uart-rx-batch [COUNT [PIN [PERIOD]]] adjacent frames (2, 0, 16)
  i2c [HEX_ADDRESS [HEX_BYTE|read [HOLD]]] (50, a5, 2)
  jtag [ir|dr [HEX_VALUE [WIDTH]]]   (dr, a5, 8)
  jtag-pair [IR_HEX [IR_WIDTH [DR_HEX [DR_WIDTH]]]] (a, 4, 12345678, 32)
  ps2 [HEX_BYTE [HOLD [IDLE_HOLD]]]  device transmit (a5, 2, 4)
  swd [read|write [HEX_ADDRESS [HEX_VALUE]]] or swd reset
  compose                           UART then SPI on disjoint pins
  verilog | stats | help
All demos use zero input levels; peer-based success/error cases are in tests.";

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let mode = args.first().map(String::as_str).unwrap_or("demo");
    if matches!(mode, "help" | "--help" | "-h") {
        println!("{USAGE}");
        return Ok(());
    }
    if mode == "verilog" {
        if args.len() != 1 {
            return Err("verilog takes no additional arguments".into());
        }
        print!(
            "{}\n{}\n{}",
            core::processor_ir()?.to_verilog("processor_step")?,
            include_str!("hdl/processor_top.v"),
            include_str!("hdl/pads.v")
        );
        return Ok(());
    }
    if mode == "poll" && args.len() <= 4 {
        let pin = Pin::new(args.get(1).map(|s| s.parse()).transpose()?.unwrap_or(0))?;
        let attempts = args.get(2).map(|s| s.parse()).transpose()?.unwrap_or(4);
        let gap = args.get(3).map(|s| s.parse()).transpose()?.unwrap_or(2);
        return demo(&protocols::poll::input_high(pin, attempts, gap)?);
    }
    if mode == "spi" && args.len() <= 4 {
        let byte = args
            .get(1)
            .map(|s| u8::from_str_radix(s, 16))
            .transpose()?
            .unwrap_or(0xa5);
        let config = protocols::spi::Config {
            clock: Pin::new(0)?,
            mosi: Pin::new(1)?,
            miso: Pin::new(2)?,
            select: Pin::new(3)?,
            mode: args.get(2).map(|s| s.parse()).transpose()?.unwrap_or(0),
            lsb_first: false,
            half_period: args.get(3).map(|s| s.parse()).transpose()?.unwrap_or(4),
        };
        return demo(&protocols::spi::transfer(byte, config)?);
    }
    if mode == "uart-rx" && args.len() <= 4 {
        let pin = Pin::new(args.get(1).map(|s| s.parse()).transpose()?.unwrap_or(0))?;
        let period = args.get(2).map(|s| s.parse()).transpose()?.unwrap_or(16);
        let attempts = args.get(3).map(|s| s.parse()).transpose()?.unwrap_or(8);
        return demo(&uart::receive(pin, period, attempts)?);
    }
    if mode == "uart-rx-batch" && args.len() <= 4 {
        let count = args.get(1).map(|s| s.parse()).transpose()?.unwrap_or(2);
        let pin = Pin::new(args.get(2).map(|s| s.parse()).transpose()?.unwrap_or(0))?;
        let period = args.get(3).map(|s| s.parse()).transpose()?.unwrap_or(16);
        return demo(&uart::receive_frames(pin, period, 16, count)?);
    }
    if mode == "stats" && args.len() == 1 {
        let ir = core::processor_ir()?;
        println!(
            "nodes={} verilog_bytes={}",
            ir.nodes().len(),
            ir.to_verilog("processor_step")?.len()
        );
        return Ok(());
    }
    if mode == "compose" && args.len() == 1 {
        use composition::{Composer, Operation};
        let mut composer = Composer::default();
        composer.push(
            Operation::single_exit("uart", uart::transmit(b"A", Pin::new(0)?, 2)?)?,
            None,
        )?;
        let spi = protocols::spi::Config {
            clock: Pin::new(1)?,
            mosi: Pin::new(2)?,
            miso: Pin::new(3)?,
            select: Pin::new(4)?,
            mode: 0,
            lsb_first: false,
            half_period: 2,
        };
        composer.push(
            Operation::single_exit("spi", protocols::spi::transfer(0x69, spi)?)?,
            None,
        )?;
        let composition = composer.finish()?;
        for location in composition.locations {
            eprintln!("{} entry={:02x}", location.name, location.entry);
        }
        return demo(&composition.program);
    }
    if mode == "swd" && args.len() <= 4 {
        let cfg = protocols::swd::Config {
            clock: Pin::new(0)?,
            data: Pin::new(1)?,
            hold: 1,
            attempts: 3,
            retry_gap: 2,
        };
        let operation = args.get(1).map(String::as_str).unwrap_or("read");
        if operation == "reset" {
            return demo(&protocols::swd::line_reset(cfg)?);
        }
        let address = args
            .get(2)
            .map(|s| u8::from_str_radix(s, 16))
            .transpose()?
            .unwrap_or(0);
        let transfer = match operation {
            "read" => protocols::swd::Transfer::Read,
            "write" => protocols::swd::Transfer::Write(
                args.get(3)
                    .map(|s| u32::from_str_radix(s, 16))
                    .transpose()?
                    .unwrap_or(0xa569963c),
            ),
            _ => return Err("SWD operation must be read, write or reset".into()),
        };
        return demo(&protocols::swd::transaction(false, address, transfer, cfg)?);
    }
    if mode == "i2c" && args.len() <= 4 {
        let address = args
            .get(1)
            .map(|s| u8::from_str_radix(s, 16))
            .transpose()?
            .unwrap_or(0x50);
        let transfer = match args.get(2).map(String::as_str) {
            Some("read") => protocols::i2c::Transfer::Read,
            value => protocols::i2c::Transfer::Write(
                value
                    .map(|s| u8::from_str_radix(s, 16))
                    .transpose()?
                    .unwrap_or(0xa5),
            ),
        };
        let config = protocols::i2c::Config {
            scl: Pin::new(0)?,
            sda: Pin::new(1)?,
            hold: args.get(3).map(|s| s.parse()).transpose()?.unwrap_or(2),
            stretch_attempts: 8,
        };
        // Low input demo intentionally exercises busy-bus error, without a peer.
        return demo(&protocols::i2c::transaction(address, transfer, config)?);
    }
    if mode == "jtag" && args.len() <= 4 {
        let kind = match args.get(1).map(String::as_str).unwrap_or("dr") {
            "ir" => protocols::jtag::RegisterKind::Instruction,
            "dr" => protocols::jtag::RegisterKind::Data,
            _ => return Err("JTAG kind must be ir or dr".into()),
        };
        let value = args
            .get(2)
            .map(|s| u32::from_str_radix(s, 16))
            .transpose()?
            .unwrap_or(0xa5);
        let width = args.get(3).map(|s| s.parse()).transpose()?.unwrap_or(8);
        let config = protocols::jtag::Config {
            tck: Pin::new(0)?,
            tms: Pin::new(1)?,
            tdi: Pin::new(2)?,
            tdo: Pin::new(3)?,
            hold: 1,
        };
        return demo(&protocols::jtag::scan(kind, value, width, config)?);
    }
    if mode == "jtag-pair" && args.len() <= 5 {
        use protocols::jtag::{Config, RegisterKind, Scan};
        let instruction = args
            .get(1)
            .map(|s| u32::from_str_radix(s, 16))
            .transpose()?
            .unwrap_or(0xa);
        let instruction_width = args.get(2).map(|s| s.parse()).transpose()?.unwrap_or(4);
        let data = args
            .get(3)
            .map(|s| u32::from_str_radix(s, 16))
            .transpose()?
            .unwrap_or(0x12345678);
        let width = args.get(4).map(|s| s.parse()).transpose()?.unwrap_or(32);
        let config = Config {
            tck: Pin::new(0)?,
            tms: Pin::new(1)?,
            tdi: Pin::new(2)?,
            tdo: Pin::new(3)?,
            hold: 1,
        };
        return demo(&protocols::jtag::sequence(
            &[
                Scan {
                    kind: RegisterKind::Instruction,
                    value: instruction,
                    width: instruction_width,
                    capture: 0,
                },
                Scan {
                    kind: RegisterKind::Data,
                    value: data,
                    width,
                    capture: 32,
                },
            ],
            config,
        )?);
    }
    if mode == "ps2" && args.len() <= 4 {
        let byte = args
            .get(1)
            .map(|s| u8::from_str_radix(s, 16))
            .transpose()?
            .unwrap_or(0xa5);
        let config = protocols::ps2::Config {
            clock: Pin::new(0)?,
            data: Pin::new(1)?,
            hold: args.get(2).map(|s| s.parse()).transpose()?.unwrap_or(2),
            idle_hold: args.get(3).map(|s| s.parse()).transpose()?.unwrap_or(4),
            attempts: 8,
        };
        return demo(&protocols::ps2::device_transmit(byte, config)?);
    }
    if !matches!(mode, "demo" | "mem" | "asm") || args.len() > 4 {
        return Err(USAGE.into());
    }
    let text = args.get(1).map(String::as_bytes).unwrap_or(b"Hi");
    let pin = Pin::new(args.get(2).map(|s| s.parse()).transpose()?.unwrap_or(0))?;
    let period = args.get(3).map(|s| s.parse()).transpose()?.unwrap_or(8);
    let program = uart::transmit(text, pin, period)?;
    match mode {
        "mem" => {
            for word in program.words() {
                println!("{word:08x}");
            }
        }
        "asm" => {
            for (pc, word) in program.words().into_iter().enumerate() {
                println!("{pc:02x}: {word:08x} {:?}", isa::Instruction::decode(word)?);
            }
        }
        _ => demo(&program)?,
    }
    Ok(())
}

fn demo(program: &isa::Program) -> Result<(), Box<dyn std::error::Error>> {
    let ir = core::processor_ir()?;
    let (outcome, trace) = runner::run(program, 2_000_000);
    let words = program.words();
    let mut expected = reference::State::default();
    for (cycle, &state) in trace.iter().enumerate() {
        let word = words[usize::from(expected.pc)];
        assert_eq!(runner::ir_step(&ir, expected, word, 0, false), state);
        expected = expected.tick(word, 0, false);
        assert_eq!(state, expected);
        println!(
            "cycle={:4} pc={:02x} wait={:5} pins={:02x} enables={:02x} halted={} fault={} scratch={:016x} count={}",
            cycle + 1,
            state.pc,
            state.wait,
            state.pins,
            state.enables,
            state.halted,
            state.fault,
            state.scratch,
            state.count
        );
    }
    if outcome != runner::Outcome::Halted {
        return Err(format!("execution ended: {outcome:?}").into());
    }
    Ok(())
}
