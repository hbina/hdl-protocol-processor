//! Untimed bit transformations authored with Rust assignments.
//!
//! ```
//! use bitlogic::{logic, bits, Bits};
//! #[logic]
//! fn invert(input: &Bits<8>, output: &mut Bits<8>) {
//!     *output = !*input;
//! }
//! let ir = invert::ir().unwrap();
//! assert_eq!(ir.evaluate(&[0x55]).unwrap(), [0xaa]);
//! assert!(ir.to_verilog("invert").unwrap().contains("module invert"));
//! let mut result = bits::<8>(0);
//! invert(&bits::<8>(0x55), &mut result);
//! assert_eq!(result.get(), 0xaa);
//! ```
//!
//! Rust checks access rights in the retained native function:
//! ```compile_fail
//! use bitlogic::{logic, Bits, bits};
//! #[logic]
//! fn copy(input: &Bits<8>, output: &mut Bits<8>) { *output = *input; }
//! let mut pin = bits::<8>(0);
//! copy(&pin, &mut pin);
//! ```
//! Outputs must be defined on every path, independently of their native initial value:
//! ```compile_fail
//! use bitlogic::{logic, Bits};
//! #[logic]
//! fn incomplete(enable: &bool, output: &mut Bits<8>) {
//!     if *enable { *output = bitlogic::bits::<8>(1); }
//! }
//! ```
//!
//! Two output parameters cannot alias in native Rust:
//! ```compile_fail
//! use bitlogic::{logic, Bits, bits};
//! #[logic]
//! fn pair(a: &mut Bits<1>, b: &mut Bits<1>) { *a = bits::<1>(0); *b = bits::<1>(1); }
//! let mut pin = bits::<1>(0);
//! pair(&mut pin, &mut pin);
//! ```
//!
//! Shared input references cannot be assigned:
//! ```compile_fail
//! use bitlogic::{logic, Bits, bits};
//! #[logic]
//! fn invalid(a: &Bits<1>, b: &mut Bits<1>) { *a = bits::<1>(0); *b = bits::<1>(1); }
//! ```

mod ir;
mod value;
pub use value::{LogicValue, Schema};
#[doc(hidden)]
pub mod __private {
    pub use crate::value::Symbolic;
}
pub use bitlogic_macros::logic;
pub use ir::{Binary, Builder, Error, Logic, Node, NodeId, Operation, Port};
use std::ops::{Add, BitAnd, BitOr, BitXor, Not, Shl, Shr, Sub};

/// An unsigned, fixed-width value. Arithmetic wraps at N bits in every build profile.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct Bits<const N: usize>(u64);

pub const fn bits<const N: usize>(value: u64) -> Bits<N> {
    assert!(N > 0 && N <= 64, "bit widths must be in 1..=64");
    Bits(value & (u64::MAX >> (64 - N)))
}

impl<const N: usize> Bits<N> {
    pub const fn get(self) -> u64 {
        self.0
    }
    pub fn bit(self, index: usize) -> bool {
        assert!(index < N, "bit index out of bounds");
        (self.0 >> index) & 1 != 0
    }
    pub fn slice<const M: usize>(self, offset: usize) -> Bits<M> {
        assert!(M > 0 && M <= N && offset <= N - M, "slice out of bounds");
        bits(self.0 >> offset)
    }
    /// Concatenate self as the high bits and rhs as the low bits.
    pub fn concat<const M: usize, const O: usize>(self, rhs: Bits<M>) -> Bits<O> {
        assert!(
            O <= 64 && N.checked_add(M) == Some(O),
            "concatenation width mismatch"
        );
        bits((self.0 << M) | rhs.0)
    }
}

macro_rules! binary {
    ($trait:ident, $method:ident, $op:expr) => {
        impl<const N: usize> $trait for Bits<N> {
            type Output = Self;
            fn $method(self, rhs: Self) -> Self {
                bits(($op)(self.0, rhs.0))
            }
        }
    };
}
binary!(BitAnd, bitand, |a, b| a & b);
binary!(BitOr, bitor, |a, b| a | b);
binary!(BitXor, bitxor, |a, b| a ^ b);
binary!(Add, add, u64::wrapping_add);
binary!(Sub, sub, u64::wrapping_sub);
impl<const N: usize> Not for Bits<N> {
    type Output = Self;
    fn not(self) -> Self {
        bits(!self.0)
    }
}
impl<const N: usize> Shl<u32> for Bits<N> {
    type Output = Self;
    fn shl(self, rhs: u32) -> Self {
        bits(self.0.checked_shl(rhs).unwrap_or(0))
    }
}
impl<const N: usize> Shr<u32> for Bits<N> {
    type Output = Self;
    fn shr(self, rhs: u32) -> Self {
        bits(self.0.checked_shr(rhs).unwrap_or(0))
    }
}
