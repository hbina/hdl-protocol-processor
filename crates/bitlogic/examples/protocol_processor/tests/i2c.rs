use super::*;
use crate::{
    assembler::Assembler,
    protocols::i2c::{self, Config, Transfer},
};

#[derive(Clone, Copy, Debug)]
struct Scenario {
    address: u8,
    transfer: Transfer,
    response: u8,
    address_ack: bool,
    data_ack: bool,
    busy: u8,
    stretch_release: usize,
    stretch_clocks: usize,
    attempts: u16,
    hold: u16,
    scl: u8,
    sda: u8,
}

// Independent target model: operates on resolved wires and SCL/SDA edges, never
// on instructions, PC, or the processor's scratch values.
struct Peer {
    scenario: Scenario,
    previous: u8,
    master_clock_low: bool,
    remaining: usize,
    releases: usize,
    data_low: bool,
    started: bool,
    starts: usize,
    stops: usize,
    group: usize,
    slot: usize,
    shift: u8,
    bytes: Vec<u8>,
    controller_nack: Option<bool>,
}

impl Peer {
    fn new(scenario: Scenario) -> Self {
        Self {
            scenario,
            previous: !scenario.busy,
            master_clock_low: false,
            remaining: 0,
            releases: 0,
            data_low: false,
            started: false,
            starts: 0,
            stops: 0,
            group: 0,
            slot: 0,
            shift: 0,
            bytes: Vec::new(),
            controller_nack: None,
        }
    }
    fn scl(&self) -> u8 {
        1 << self.scenario.scl
    }
    fn sda(&self) -> u8 {
        1 << self.scenario.sda
    }
    fn external(&self, state: State) -> u8 {
        // A stretching target pre-arms while SCL is low, so release cannot
        // produce a spurious rising edge before the stretch takes effect.
        let armed = self.started
            && state.enables & self.scl() != 0
            && self.releases + 1 == self.scenario.stretch_release;
        self.scenario.busy
            | if self.data_low { self.sda() } else { 0 }
            | if self.remaining > 0 || armed {
                self.scl()
            } else {
                0
            }
    }
    fn resolve(state: State, external: u8) -> u8 {
        assert_eq!(
            state.pins & state.enables & external,
            0,
            "opposing active drivers"
        );
        !(state.enables & !state.pins | external)
    }
    fn observe_bus(&mut self, levels: u8, state: State) {
        let old_scl = self.previous & self.scl() != 0;
        let scl = levels & self.scl() != 0;
        let old_sda = self.previous & self.sda() != 0;
        let sda = levels & self.sda() != 0;
        if old_scl && scl && old_sda != sda {
            if !sda {
                assert!(!self.started, "unexpected START during a byte");
                self.started = true;
                self.starts += 1;
                self.group = 0;
                self.slot = 0;
                self.shift = 0;
            } else {
                self.started = false;
                self.stops += 1;
            }
        }
        if self.started && !old_scl && scl {
            if self.slot < 8 {
                self.shift = (self.shift << 1) | u8::from(sda);
                if self.group == 1
                    && self.scenario.address_ack
                    && matches!(self.scenario.transfer, Transfer::Read)
                {
                    assert_eq!(
                        state.enables & self.sda(),
                        0,
                        "controller drove during target read"
                    );
                }
                if self.slot == 7 {
                    self.bytes.push(self.shift);
                }
            } else if self.group == 1 && matches!(self.scenario.transfer, Transfer::Read) {
                self.controller_nack = Some(sda);
            }
            self.slot += 1;
        }
        if self.started && old_scl && !scl {
            if self.slot == 9 {
                self.slot = 0;
                self.group += 1;
                self.shift = 0;
            }
            self.data_low = if self.slot == 8 {
                if self.group == 0 {
                    self.scenario.address_ack
                } else {
                    matches!(self.scenario.transfer, Transfer::Write(_)) && self.scenario.data_ack
                }
            } else if self.group == 1
                && self.slot < 8
                && self.scenario.address_ack
                && matches!(self.scenario.transfer, Transfer::Read)
            {
                self.scenario.response & (1 << (7 - self.slot)) == 0
            } else {
                false
            };
        }
        self.previous = levels;
    }
    fn advance(&mut self, state: State, previous_external: u8) {
        let low = state.enables & self.scl() != 0;
        if self.master_clock_low && !low && self.started {
            self.releases += 1;
            if self.releases == self.scenario.stretch_release {
                self.remaining = self.scenario.stretch_clocks;
            }
        } else if !low {
            self.remaining = self.remaining.saturating_sub(1);
        }
        self.master_clock_low = low;
        self.observe_bus(Self::resolve(state, previous_external), state);
        self.observe_bus(Self::resolve(state, self.external(state)), state);
    }
}

fn scenario(mut case: Scenario, ir: &bitlogic::Logic, hdl: &mut ClockedVectors) -> usize {
    // Busy is a physical mask, with pins chosen by the scenario.
    if case.busy == 1 {
        case.busy = 1 << case.scl;
    } else if case.busy == 2 {
        case.busy = 1 << case.sda;
    }
    let cfg = Config {
        scl: Pin::new(case.scl).unwrap(),
        sda: Pin::new(case.sda).unwrap(),
        hold: case.hold,
        stretch_attempts: case.attempts,
    };
    let program = i2c::transaction(case.address, case.transfer, cfg).unwrap();
    assert!(program.instructions().len() <= 256);
    let words = program.words();
    let mut state = State::default();
    let mut peer = Peer::new(case);
    hdl.load(&words);
    hdl.edge(true, 0, state);
    let mask = (1 << case.scl) | (1 << case.sda);
    let mut cycles = 0;
    for _ in 0..10000 {
        let external = peer.external(state);
        let inputs = Peer::resolve(state, external);
        let word = words[usize::from(state.pc)];
        let next = state.tick(word, inputs, false);
        assert_eq!(native_step(state, word, inputs, false), next);
        assert_eq!(ir_step(ir, state, word, inputs, false), next);
        assert_eq!(next.pins & mask, 0, "I2C must never drive high");
        hdl.bus_edge(external, inputs, mask, false, next);
        state = next;
        peer.advance(state, external);
        cycles += 1;
        if state.halted {
            break;
        }
    }
    assert!(state.halted && !state.fault, "{case:?}: {state:?}");
    assert_eq!(
        state.enables & mask,
        0,
        "bus must be released on every exit"
    );
    let timeout = case.stretch_clocks > 0
        && case.stretch_release != 0
        && case.stretch_clocks > usize::from(case.attempts) * 3 - 2;
    let nack = !case.address_ack || (matches!(case.transfer, Transfer::Write(_)) && !case.data_ack);
    let expected_flags = if case.busy != 0 {
        (1_u64 << 63) | (1 << 60)
    } else if timeout {
        (1 << 63) | (1 << 59)
    } else if nack {
        (1 << 63) | (1 << 61)
    } else {
        1 << 62
    };
    assert_eq!(state.scratch & (31 << 59), expected_flags, "{case:?}");
    if case.busy != 0 {
        assert_eq!(peer.starts, 0);
    } else {
        assert_eq!(peer.starts, 1, "{case:?}");
        if !timeout {
            assert_eq!(peer.stops, 1, "{case:?}");
            assert_eq!(
                peer.bytes[0],
                (case.address << 1) | u8::from(matches!(case.transfer, Transfer::Read))
            );
            if case.address_ack {
                match case.transfer {
                    Transfer::Write(byte) => assert_eq!(peer.bytes[1], byte),
                    Transfer::Read => {
                        assert_eq!((state.scratch >> 32) as u8, case.response);
                        assert_eq!(peer.controller_nack, Some(true));
                    }
                }
            }
        }
    }
    cycles
}

#[test]
fn resolved_i2c_transactions_stretch_nack_busy_and_timeout() {
    let ir = processor_ir().unwrap();
    let mut hdl = ClockedVectors::new();
    let base = Scenario {
        address: 0x50,
        transfer: Transfer::Write(0xa5),
        response: 0x69,
        address_ack: true,
        data_ack: true,
        busy: 0,
        stretch_release: 0,
        stretch_clocks: 0,
        attempts: 8,
        hold: 1,
        scl: 0,
        sda: 1,
    };
    let mut cases = 0;
    for byte in 0..=255 {
        scenario(
            Scenario {
                transfer: Transfer::Write(byte),
                ..base
            },
            &ir,
            &mut hdl,
        );
        cases += 1;
        scenario(
            Scenario {
                transfer: Transfer::Read,
                response: byte,
                ..base
            },
            &ir,
            &mut hdl,
        );
        cases += 1;
    }
    for address in 0x08..=0x77 {
        scenario(
            Scenario {
                address,
                scl: 6,
                sda: 7,
                ..base
            },
            &ir,
            &mut hdl,
        );
        cases += 1;
    }
    for release in 1..=19 {
        for transfer in [Transfer::Write(0x69), Transfer::Read] {
            scenario(
                Scenario {
                    transfer,
                    stretch_release: release,
                    stretch_clocks: 10,
                    ..base
                },
                &ir,
                &mut hdl,
            );
            cases += 1;
        }
    }
    for transfer in [Transfer::Write(0x96), Transfer::Read] {
        for address_ack in [false, true] {
            scenario(
                Scenario {
                    transfer,
                    address_ack,
                    data_ack: false,
                    hold: 3,
                    ..base
                },
                &ir,
                &mut hdl,
            );
            cases += 1;
        }
        for busy in [1, 2] {
            scenario(
                Scenario {
                    transfer,
                    busy,
                    ..base
                },
                &ir,
                &mut hdl,
            );
            cases += 1;
        }
        for release in [1, 9, 18, 19] {
            scenario(
                Scenario {
                    transfer,
                    stretch_release: release,
                    stretch_clocks: 1000,
                    ..base
                },
                &ir,
                &mut hdl,
            );
            cases += 1;
        }
    }
    for attempts in [1, 2, 8] {
        for clocks in [usize::from(attempts) * 3 - 2, usize::from(attempts) * 3 - 1] {
            scenario(
                Scenario {
                    attempts,
                    stretch_release: 1,
                    stretch_clocks: clocks,
                    ..base
                },
                &ir,
                &mut hdl,
            );
            cases += 1;
        }
    }
    println!("{cases} independent resolved-bus I2C scenarios");
    hdl.finish();
}

#[test]
fn i2c_reset_releases_drivers() {
    let config = Config {
        scl: Pin::new(0).unwrap(),
        sda: Pin::new(1).unwrap(),
        hold: 2,
        stretch_attempts: 8,
    };
    let words = i2c::transaction(0x50, Transfer::Write(0), config)
        .unwrap()
        .words();
    let mut hdl = ClockedVectors::new();
    hdl.load(&words);
    let mut state = State::default();
    hdl.edge(true, 0, state);
    // Idle bus, no target ACK needed before the first data phase.
    for _ in 0..40 {
        let inputs = Peer::resolve(state, 0);
        state = state.tick(words[usize::from(state.pc)], inputs, false);
        hdl.bus_edge(0, inputs, 3, false, state);
        if state.enables & 1 != 0 {
            break;
        }
    }
    assert_ne!(state.enables, 0);
    let inputs = Peer::resolve(state, 0);
    hdl.bus_edge(0, inputs, 3, true, State::default());
    hdl.bus_edge(0, 255, 3, true, State::default());
    hdl.finish();
}

#[test]
fn checked_assembly_and_pin_configuration() {
    let mut a = Assembler::default();
    a.label("start").unwrap();
    assert!(a.label("start").is_err());
    let mut a = Assembler::default();
    a.jump("missing");
    a.emit(Instruction::Halt);
    assert!(a.finish().is_err());
    let mut a = Assembler::default();
    a.jump("end");
    for _ in 0..255 {
        a.emit(Instruction::Halt);
    }
    a.label("end").unwrap();
    a.emit(Instruction::Halt);
    assert!(a.finish().is_err());
    let mut a = Assembler::default();
    a.delay(0);
    a.jump("done");
    a.emit(Instruction::Halt);
    a.label("done").unwrap();
    a.emit(Instruction::Halt);
    assert_eq!(
        a.finish().unwrap().words(),
        [0x60000002, 0xf0000000, 0xf0000000]
    );
    let instruction = Instruction::ConfigurePins {
        mask: 0x81,
        enables: 255,
        value: 0x55,
    };
    assert_eq!(instruction.encode(), 0xb0818101);
    assert_eq!(
        Instruction::decode(instruction.encode()).unwrap().encode(),
        instruction.encode()
    );
    assert!(Instruction::decode(0xb1000000).is_err());
    let before = State {
        pc: 1,
        enables: 0x55,
        pins: 0xaa,
        ..State::default()
    };
    let after = before.tick(instruction.encode(), 0, false);
    assert_eq!((after.pc, after.enables, after.pins), (2, 0xd5, 0x2b));
    assert_eq!(after.tick(0, 0, true), State::default());
    let config = Config {
        scl: Pin::new(0).unwrap(),
        sda: Pin::new(1).unwrap(),
        hold: 1,
        stretch_attempts: 1,
    };
    for address in (0..8).chain(0x78..=255) {
        assert!(i2c::transaction(address, Transfer::Read, config).is_err());
    }
    assert!(
        i2c::transaction(
            0x50,
            Transfer::Read,
            Config {
                sda: config.scl,
                ..config
            }
        )
        .is_err()
    );
    assert!(i2c::transaction(0x50, Transfer::Read, Config { hold: 0, ..config }).is_err());
    assert!(
        i2c::transaction(
            0x50,
            Transfer::Read,
            Config {
                stretch_attempts: 0,
                ..config
            }
        )
        .is_err()
    );
}
