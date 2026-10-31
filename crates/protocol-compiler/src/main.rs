use std::{error::Error, num::NonZeroU16, path::PathBuf};

use protocol_isa::Pin;

const USAGE: &str = "Usage: protocol-compiler uart-tx --pin N --cycles-per-bit N --text TEXT [--format memh|asm] [--output FILE]\nCompiles annotated Rust to instructions; default output is 32-bit hexadecimal words.\ncycles-per-bit must be 1..=65535.";

fn run() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args().skip(1);
    let Some(command) = args.next() else {
        return Err(USAGE.into());
    };
    if command == "--help" || command == "-h" {
        println!("{USAGE}");
        return Ok(());
    }
    if command != "uart-tx" {
        return Err(USAGE.into());
    }
    let (mut pin, mut period, mut text, mut output, mut format) = (None, None, None, None, None);
    while let Some(flag) = args.next() {
        let value = args.next().ok_or("missing option value")?;
        match flag.as_str() {
            "--pin" if pin.is_none() => pin = Some(Pin::new(value.parse()?)?),
            "--cycles-per-bit" if period.is_none() => {
                period = Some(value.parse::<NonZeroU16>()?);
            }
            "--text" if text.is_none() => text = Some(value),
            "--output" if output.is_none() => output = Some(PathBuf::from(value)),
            "--format" if format.is_none() && ["memh", "asm"].contains(&value.as_str()) => {
                format = Some(value);
            }
            _ => return Err(format!("unknown or repeated option: {flag}").into()),
        }
    }
    let program = protocol_compiler::uart_tx::compile(
        text.ok_or("--text is required")?.as_bytes(),
        pin.ok_or("--pin is required")?,
        period.ok_or("--cycles-per-bit is required")?,
    )?;
    let image = if format.as_deref() == Some("asm") {
        program.to_assembly()
    } else {
        program.to_memh()
    };
    if let Some(path) = output {
        if let Some(parent) = path.parent().filter(|p| !p.as_os_str().is_empty()) {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::write(path, image)?;
    } else {
        print!("{image}");
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(2);
    }
}
