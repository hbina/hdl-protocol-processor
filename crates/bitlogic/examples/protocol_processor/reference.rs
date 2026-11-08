//! Independent integer-based execution specification. No DSL or ISA decoder calls.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct State {
    pub pc: u8,
    pub wait: u16,
    pub pins: u8,
    pub halted: bool,
    pub fault: bool,
    pub scratch: u64,
    pub count: u16,
    pub enables: u8,
}

impl State {
    pub fn tick(self, word: u32, inputs: u8, reset: bool) -> Self {
        if reset {
            return Self::default();
        }
        if self.halted {
            return self;
        }
        if self.wait != 0 {
            return Self {
                wait: self.wait - 1,
                ..self
            };
        }
        let mut next = self;
        let opcode = word / 0x1000_0000;
        let payload = word % 0x1000_0000;
        let valid = match opcode {
            1 => payload < 65536,
            2 => (1..65536).contains(&payload),
            3 => payload < 4194304,
            4 => payload == 0,
            5 | 10 => payload < 512,
            6 | 9 => payload < 256,
            7 => payload < 32768,
            8 => payload < 65536,
            11 => payload < 16777216,
            12 => payload < 33554432,
            13 => payload.is_multiple_of(65536) && payload / 65536 < 64,
            15 => payload == 0,
            _ => false,
        };
        let branch_bit = (self.scratch / 2_u64.pow(payload / 256 % 64)) % 2;
        let jumps = opcode == 6
            || (opcode == 7 && branch_bit == u64::from(payload / 16384 % 2))
            || (opcode == 9 && self.count > 1);
        if !valid || (opcode != 15 && !jumps && self.pc == 255) {
            next.halted = true;
            next.fault = true;
            return next;
        }
        match opcode {
            1 => {
                // Deliberately update individual pins rather than using the core's formula.
                for pin in 0..8 {
                    let place = 2_u32.pow(pin);
                    if (payload / 256 / place) % 2 == 1 {
                        if (payload / place) % 2 == 1 {
                            next.pins |= place as u8;
                        } else {
                            next.pins &= !(place as u8);
                        }
                    }
                }
                next.pc += 1;
            }
            2 => {
                next.wait = (payload - 1) as u16;
                next.pc += 1;
            }
            15 => next.halted = true,
            3 => {
                let lhs = (self.scratch / 2_u64.pow(payload / 1024 % 64)) % 2;
                let rhs = (self.scratch / 2_u64.pow(payload / 16 % 64)) % 2;
                let dst = payload / 65536 % 64;
                let result = (payload % 16 / 2_u32.pow((2 * lhs + rhs) as u32)) % 2;
                next.scratch &= !2_u64.pow(dst);
                if result == 1 {
                    next.scratch |= 2_u64.pow(dst);
                }
                next.pc += 1;
            }
            4 => {
                next.scratch = inputs.into();
                next.pc += 1;
            }
            5 => {
                let value = (self.scratch / 2_u64.pow(payload / 8)) % 2;
                let pin = 2_u8.pow(payload % 8);
                next.pins &= !pin;
                if value == 1 {
                    next.pins |= pin;
                }
                next.pc += 1;
            }
            6 | 7 => {
                next.pc = if jumps { payload as u8 } else { self.pc + 1 };
            }
            8 => {
                next.count = payload as u16;
                next.pc += 1;
            }
            9 => {
                next.count = self.count.saturating_sub(1);
                next.pc = if jumps { payload as u8 } else { self.pc + 1 };
            }
            10 | 12 => {
                let value = (u32::from(inputs) / 2_u32.pow(payload % 8)) % 2;
                let mask = 2_u64.pow(payload / 8 % 64);
                next.scratch &= !mask;
                if value == 1 {
                    next.scratch |= mask;
                }
                if opcode == 12 {
                    for pin in 0..8 {
                        let place = 2_u32.pow(pin);
                        if (payload / 131072 / place) % 2 == 1 {
                            next.pins &= !(place as u8);
                            if (payload / 512 / place) % 2 == 1 {
                                next.pins |= place as u8;
                            }
                        }
                    }
                }
                next.pc += 1;
            }
            11 => {
                for pin in 0..8 {
                    let place = 2_u32.pow(pin);
                    if (payload / 65536 / place) % 2 == 1 {
                        next.pins &= !(place as u8);
                        next.enables &= !(place as u8);
                        if (payload / place) % 2 == 1 {
                            next.pins |= place as u8;
                        }
                        if (payload / 256 / place) % 2 == 1 {
                            next.enables |= place as u8;
                        }
                    }
                }
                next.pc += 1;
            }
            13 => {
                let odd = !(self.scratch / 4294967296).count_ones().is_multiple_of(2);
                let mask = 2_u64.pow(payload / 65536);
                next.scratch &= !mask;
                if odd {
                    next.scratch |= mask;
                }
                next.pc += 1;
            }
            _ => unreachable!(),
        }
        next
    }

    pub fn values(self) -> [u64; 8] {
        [
            self.pc.into(),
            self.wait.into(),
            self.pins.into(),
            self.halted.into(),
            self.fault.into(),
            self.scratch,
            self.count.into(),
            self.enables.into(),
        ]
    }
}
