//! Rust protocol functions compiled to pin-processor assembly using `#[protocol]`.
//!
//! The macro retains an executable Rust function and generates a same-named type:
//! ```
//! use protocol_compiler::{protocol, drive, wait, simulate, Pin};
//! #[protocol]
//! fn pulse(pin: Pin, high: bool) {
//!     let duration = 3_u16;
//!     drive(pin, high);
//!     wait(duration);
//!     drive(pin, !high);
//! }
//! let pin = Pin::new(0).unwrap();
//! let program = pulse::compile(pin, true).unwrap();
//! let native = simulate(|| pulse(pin, true)).unwrap();
//! assert_eq!(native.effects.as_slice(), pulse::ir(pin, true).unwrap().effects());
//! assert_eq!(program.instructions().len(), 4); // SET, WAIT, SET, HALT
//! ```
//!
//! Unsupported control flow is rejected at macro expansion:
//! ```compile_fail
//! use protocol_compiler::protocol;
//! #[protocol]
//! fn unbounded() { loop {} }
//! ```
//!
//! Effect types are checked by Rust:
//! ```compile_fail
//! use protocol_compiler::{protocol, drive, Pin};
//! #[protocol]
//! fn bad(pin: Pin) { drive(pin, 42); }
//! ```
extern crate self as protocol_compiler;

mod frontend;
pub use frontend::{CompileError, Effect, ProtocolIr, Trace, drive, simulate, wait};
pub use protocol_isa::{Pin, Program};
pub use protocol_macros::protocol;
use std::num::NonZeroU16;

#[protocol]
fn uart_bit(pin: Pin, high: bool, period: NonZeroU16) {
    drive(pin, high);
    // DRIVE takes one clock; the remaining clocks are an explicit wait.
    wait(period.get() - 1);
}

/// UART 8N1: one idle interval, then start/data/stop for each byte.
/// All arguments are specialized on the host when `uart_tx::compile` is called.
#[protocol]
pub fn uart_tx(bytes: &[u8], pin: Pin, cycles_per_bit: NonZeroU16) {
    uart_bit(pin, true, cycles_per_bit);
    for &byte in bytes {
        uart_bit(pin, false, cycles_per_bit);
        for index in 0..8 {
            let high = byte & (1 << index) != 0;
            uart_bit(pin, high, cycles_per_bit);
        }
        uart_bit(pin, true, cycles_per_bit);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_programs_larger_than_instruction_memory() {
        let pin = Pin::new(0).unwrap();
        let slow = NonZeroU16::new(8).unwrap();
        let fast = NonZeroU16::new(1).unwrap();
        assert!(uart_tx::compile(&[0; 12], pin, slow).is_ok());
        assert!(uart_tx::compile(&[0; 13], pin, slow).is_err());
        assert!(uart_tx::compile(&[0; 25], pin, fast).is_ok());
        assert!(uart_tx::compile(&[0; 26], pin, fast).is_err());
        assert_eq!(
            uart_tx::compile(&[], pin, slow)
                .unwrap()
                .instructions()
                .len(),
            3
        );
    }
}
