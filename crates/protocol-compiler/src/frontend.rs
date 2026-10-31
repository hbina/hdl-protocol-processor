//! Typed effect IR, instruction lowering, and native Rust trace capture.
use std::{cell::RefCell, error::Error, fmt, num::NonZeroU16};

use protocol_isa::{Instruction, Pin, Program, ProgramError};

const MAX_WORK: usize = 65_536;
const MAX_CALL_DEPTH: usize = 32;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CompileError(pub String);

impl fmt::Display for CompileError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl Error for CompileError {}

impl From<ProgramError> for CompileError {
    fn from(error: ProgramError) -> Self {
        Self(error.to_string())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Effect {
    Drive { pin: Pin, high: bool },
    Wait(u16),
}

/// Specialized, ordered effects. Pure Rust computations consume no target cycles.
#[derive(Debug)]
pub struct ProtocolIr {
    name: &'static str,
    effects: Vec<Effect>,
    iterations: usize,
    calls: Vec<&'static str>,
}

impl ProtocolIr {
    #[doc(hidden)]
    pub fn new(name: &'static str) -> Self {
        Self {
            name,
            effects: Vec::new(),
            iterations: 0,
            calls: Vec::new(),
        }
    }

    pub fn effects(&self) -> &[Effect] {
        &self.effects
    }

    #[doc(hidden)]
    pub fn enter(&mut self, name: &'static str) -> Result<(), CompileError> {
        if self.calls.len() >= MAX_CALL_DEPTH {
            return Err(self.error("protocol helper call depth exceeded (possible recursion)"));
        }
        self.calls.push(name);
        Ok(())
    }

    #[doc(hidden)]
    pub fn leave(&mut self) {
        self.calls.pop();
    }

    #[doc(hidden)]
    pub fn iteration(&mut self) -> Result<(), CompileError> {
        if self.iterations >= MAX_WORK {
            return Err(self.error("protocol compilation exceeded 65536 loop iterations"));
        }
        self.iterations += 1;
        Ok(())
    }

    #[doc(hidden)]
    pub fn drive(&mut self, pin: Pin, high: bool) -> Result<(), CompileError> {
        self.push(Effect::Drive { pin, high })
    }

    #[doc(hidden)]
    pub fn wait(&mut self, cycles: u16) -> Result<(), CompileError> {
        self.push(Effect::Wait(cycles))
    }

    fn push(&mut self, effect: Effect) -> Result<(), CompileError> {
        if self.effects.len() >= MAX_WORK {
            return Err(self.error("protocol compilation exceeded 65536 effects"));
        }
        self.effects.push(effect);
        Ok(())
    }

    fn error(&self, message: &str) -> CompileError {
        CompileError(format!(
            "protocol {} (in {}): {message}",
            self.name,
            self.calls.last().unwrap_or(&self.name)
        ))
    }

    /// Drop zero waits and coalesce consecutive waits without changing duration.
    /// Drives always remain, even when redundant: every drive consumes one cycle.
    pub fn lower(&self) -> Result<Program, CompileError> {
        let mut instructions = Vec::new();
        let mut pending_wait = 0_u64;
        let flush = |pending: &mut u64, instructions: &mut Vec<Instruction>| {
            while *pending != 0 {
                let chunk = (*pending).min(u16::MAX.into()) as u16;
                instructions.push(Instruction::Wait(NonZeroU16::new(chunk).unwrap()));
                *pending -= u64::from(chunk);
            }
        };
        for effect in &self.effects {
            match *effect {
                Effect::Wait(cycles) => pending_wait += u64::from(cycles),
                Effect::Drive { pin, high } => {
                    flush(&mut pending_wait, &mut instructions);
                    instructions.push(Instruction::SetPins {
                        mask: pin.mask(),
                        value: if high { pin.mask() } else { 0 },
                    });
                }
            }
        }
        flush(&mut pending_wait, &mut instructions);
        instructions.push(Instruction::Halt);
        Program::new(instructions).map_err(|error| self.error(&error.to_string()))
    }
}

/// A direct execution of the original Rust function, before instruction lowering.
#[derive(Debug, PartialEq, Eq)]
pub struct Trace {
    pub effects: Vec<Effect>,
}

struct Capture {
    effects: Vec<Effect>,
    overflow: bool,
}

thread_local! {
    static CAPTURE: RefCell<Option<Capture>> = const { RefCell::new(None) };
}

struct CaptureGuard;
impl Drop for CaptureGuard {
    fn drop(&mut self) {
        CAPTURE.with(|capture| {
            capture.borrow_mut().take();
        });
    }
}

/// Execute native Rust effects for comparison with compiled instructions.
/// Native panics propagate; the capture is cleared while unwinding.
pub fn simulate(run: impl FnOnce()) -> Result<Trace, CompileError> {
    CAPTURE.with(|capture| {
        if capture.borrow().is_some() {
            return Err(CompileError(
                "nested protocol simulation is not supported".into(),
            ));
        }
        *capture.borrow_mut() = Some(Capture {
            effects: Vec::new(),
            overflow: false,
        });
        Ok(())
    })?;
    let _guard = CaptureGuard;
    run();
    let capture = CAPTURE.with(|capture| capture.borrow_mut().take().unwrap());
    if capture.overflow {
        return Err(CompileError(
            "native protocol trace exceeded 65536 effects".into(),
        ));
    }
    Ok(Trace {
        effects: capture.effects,
    })
}

fn record(effect: Effect) {
    CAPTURE.with(|capture| {
        let mut capture = capture.borrow_mut();
        let capture = capture
            .as_mut()
            .expect("run native protocols inside simulate(|| ...)");
        if capture.effects.len() >= MAX_WORK {
            capture.overflow = true;
        } else {
            capture.effects.push(effect);
        }
    });
}

/// Drive one output pin; consumes one processor clock.
pub fn drive(pin: Pin, high: bool) {
    record(Effect::Drive { pin, high });
}

/// Hold pin values for this many additional clocks. Zero is a source-level no-op.
pub fn wait(cycles: u16) {
    record(Effect::Wait(cycles));
}
