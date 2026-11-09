//! CRC-8 of exactly four bytes, entirely combinational.
//!
//! Polynomial 0x07, initial CRC zero, MSB first, no reflection or final XOR.
//! The first byte occupies message[31:24]; all four bytes, including zeros,
//! participate. The bounded fold expands into logic, not clock cycles.
//! No state register, byte counter, valid, start, or last signal is needed.
use bitlogic::{Bits, LogicValue, bits, logic};

#[derive(Clone, Copy, LogicValue)]
struct Input {
    message: Bits<32>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, LogicValue)]
struct Output {
    crc: Bits<8>,
}

#[derive(Clone, Copy, LogicValue)]
struct FoldState {
    remaining: Bits<32>,
    crc: Bits<8>,
}

#[logic]
#[allow(
    dead_code,
    reason = "Artifact export uses the IR; native evaluation remains available to tests."
)]
fn crc4(input: Input) -> Output {
    let result = FoldState {
        remaining: input.message,
        crc: bits::<8>(0),
    }
    .fold::<32>(|state, _index| FoldState {
        remaining: state.remaining << 1,
        crc: if state.crc.bit(7) ^ state.remaining.bit(31) {
            (state.crc << 1) ^ bits::<8>(0x07)
        } else {
            state.crc << 1
        },
    });
    Output { crc: result.crc }
}

mod support;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    support::no_arguments()?;
    support::generate("crc4", &crc4::ir()?, &[])?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{fmt::Write, process::Command};

    // Independent polynomial long division: message * x^8 modulo x^8+x^2+x+1.
    fn expected(message: u32) -> u64 {
        let mut dividend = u64::from(message) << 8;
        for degree in (8..40).rev() {
            if dividend & (1_u64 << degree) != 0 {
                dividend ^= 0x107_u64 << (degree - 8);
            }
        }
        dividend
    }

    fn messages() -> Vec<u32> {
        let mut messages = vec![0, u32::MAX, u32::from_be_bytes(*b"1234")];
        messages.extend((0..32).map(|bit| 1_u32 << bit));
        let mut value = 0x1234_5678_u32;
        for _ in 0..4096 {
            value = value.wrapping_mul(1664525).wrapping_add(1013904223);
            messages.push(value);
        }
        messages
    }

    #[test]
    fn native_and_ir_match_polynomial_division() {
        assert_eq!(expected(0), 0);
        assert_eq!(expected(1), 7);
        let ir = crc4::ir().unwrap();
        for message in messages() {
            let input = Input {
                message: bits(message.into()),
            };
            let output = Output {
                crc: bits(expected(message)),
            };
            assert_eq!(crc4(input), output, "message={message:08x}");
            assert_eq!(ir.evaluate_typed::<_, Output>(input).unwrap(), output);
        }
    }

    #[test]
    fn emitted_hdl_matches_polynomial_division() {
        let mut source = crc4::ir().unwrap().to_verilog("crc4").unwrap();
        source.push_str(
            "module tb; reg [31:0] message; wire [7:0] crc;\n\
             crc4 dut(.i_message(message), .o_crc(crc));\ninitial begin\n",
        );
        let messages = messages();
        for &message in &messages {
            writeln!(
                source,
                "message=32'h{message:08x};#1;if(crc!==8'd{}) \
                 $fatal(1,\"CRC mismatch: message={message:08x}\");",
                expected(message)
            )
            .unwrap();
        }
        let marker = format!("CRC PASS: {} messages", messages.len());
        writeln!(source, "$display(\"{marker}\");$finish;end endmodule").unwrap();
        let dir = tempfile::tempdir().unwrap();
        let hdl = dir.path().join("crc.v");
        let executable = dir.path().join("crc.vvp");
        std::fs::write(&hdl, source).unwrap();
        let output = Command::new("iverilog")
            .args(["-g2012", "-s", "tb", "-o"])
            .arg(&executable)
            .arg(hdl)
            .output()
            .expect("Icarus Verilog is required");
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        let output = Command::new("vvp").arg(executable).output().unwrap();
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(
            output.status.success() && stdout.contains(&marker),
            "{stdout}\n{}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
}
