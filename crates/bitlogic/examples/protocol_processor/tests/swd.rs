use super::*;
use crate::protocols::swd::{self, Config, Transfer};

#[derive(Clone, Copy, Debug)]
struct Case {
    read: bool,
    ap: bool,
    address: u8,
    value: u32,
    waits: usize,
    ack: u8,
    bad_parity: bool,
    attempts: u16,
    hold: u16,
    clock: u8,
    data: u8,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Phase {
    Idle,
    Request(usize),
    OutwardTurn,
    Ack(usize),
    Read(usize),
    ReadParity,
    Write(usize),
    WriteParity,
    Backoff(usize),
    Return(bool),
}
struct Target {
    case: Case,
    phase: Phase,
    clock: bool,
    drive: Option<bool>,
    request: Vec<bool>,
    requests: usize,
    ack: u8,
    write: u32,
    writes: Vec<u32>,
}
impl Target {
    fn new(case: Case) -> Self {
        Self {
            case,
            phase: Phase::Idle,
            clock: false,
            drive: None,
            request: vec![],
            requests: 0,
            ack: 0,
            write: 0,
            writes: vec![],
        }
    }
    fn mask(&self) -> u8 {
        1 << self.case.data
    }
    fn resolve(&self, state: State) -> u8 {
        let target_en = if self.drive.is_some() { self.mask() } else { 0 };
        assert_eq!(
            state.enables & target_en,
            0,
            "SWD simultaneous ownership {:?}",
            self.phase
        );
        let target_low = if self.drive == Some(false) {
            self.mask()
        } else {
            0
        };
        !(state.enables & !state.pins | target_low)
    }
    fn advance(&mut self, state: State) {
        let clock = state.pins & (1 << self.case.clock) != 0;
        let host_data = state.pins & self.mask() != 0;
        let host_enabled = state.enables & self.mask() != 0;
        if !self.clock && clock {
            self.phase = match self.phase {
                Phase::Idle => {
                    assert!(host_enabled);
                    if host_data {
                        self.request = vec![true];
                        Phase::Request(1)
                    } else {
                        Phase::Idle
                    }
                }
                Phase::Request(n) => {
                    assert!(host_enabled);
                    self.request.push(host_data);
                    if n == 7 {
                        let q = &self.request;
                        assert!(q[0] && !q[6] && q[7]);
                        assert_eq!(q[1], self.case.ap);
                        assert_eq!(q[2], self.case.read);
                        assert_eq!(u8::from(q[3]) * 4 + u8::from(q[4]) * 8, self.case.address);
                        assert_eq!(q[1..=5].iter().filter(|&&bit| bit).count() % 2, 0);
                        self.ack = if self.requests < self.case.waits {
                            2
                        } else {
                            self.case.ack
                        };
                        self.requests += 1;
                        Phase::OutwardTurn
                    } else {
                        Phase::Request(n + 1)
                    }
                }
                Phase::OutwardTurn => {
                    assert!(!host_enabled);
                    assert!(self.drive.is_none());
                    Phase::Ack(0)
                }
                Phase::Ack(n) => {
                    assert!(!host_enabled);
                    assert_eq!(self.drive, Some(self.ack & (1 << n) != 0));
                    if n < 2 {
                        Phase::Ack(n + 1)
                    } else if self.ack == 1 {
                        if self.case.read {
                            Phase::Read(0)
                        } else {
                            Phase::Return(true)
                        }
                    } else if matches!(self.ack, 2 | 4) {
                        Phase::Return(false)
                    } else {
                        Phase::Backoff(33)
                    }
                }
                Phase::Read(n) => {
                    assert!(!host_enabled);
                    if n == 31 {
                        Phase::ReadParity
                    } else {
                        Phase::Read(n + 1)
                    }
                }
                Phase::ReadParity => {
                    assert!(!host_enabled);
                    Phase::Return(false)
                }
                Phase::Return(write) => {
                    assert!(!host_enabled);
                    assert!(self.drive.is_none());
                    if write {
                        self.write = 0;
                        Phase::Write(0)
                    } else {
                        Phase::Idle
                    }
                }
                Phase::Write(n) => {
                    assert!(host_enabled);
                    if host_data {
                        self.write |= 1 << n;
                    }
                    if n == 31 {
                        Phase::WriteParity
                    } else {
                        Phase::Write(n + 1)
                    }
                }
                Phase::WriteParity => {
                    assert!(host_enabled);
                    assert_eq!(host_data, self.write.count_ones() % 2 == 1);
                    assert_eq!(self.write, self.case.value);
                    self.writes.push(self.write);
                    Phase::Idle
                }
                Phase::Backoff(n) => {
                    assert!(!host_enabled);
                    if n == 1 {
                        Phase::Return(false)
                    } else {
                        Phase::Backoff(n - 1)
                    }
                }
            };
        }
        if self.clock && !clock {
            self.drive = match self.phase {
                Phase::Ack(n) => Some(self.ack & (1 << n) != 0),
                Phase::Read(n) => Some(self.case.value & (1 << n) != 0),
                Phase::ReadParity => {
                    Some((self.case.value.count_ones() % 2 == 1) ^ self.case.bad_parity)
                }
                Phase::Backoff(n) => Some(n % 2 == 0),
                _ => None,
            };
        }
        self.clock = clock;
    }
}

fn check(case: Case, ir: &bitlogic::Logic, hdl: &mut ClockedVectors) {
    let cfg = Config {
        clock: Pin::new(case.clock).unwrap(),
        data: Pin::new(case.data).unwrap(),
        hold: case.hold,
        attempts: case.attempts,
        retry_gap: 2,
    };
    let transfer = if case.read {
        Transfer::Read
    } else {
        Transfer::Write(case.value)
    };
    let program = swd::transaction(case.ap, case.address, transfer, cfg).unwrap();
    let words = program.words();
    let mut target = Target::new(case);
    let mut state = State::default();
    hdl.load(&words);
    hdl.edge(true, 0, state);
    for _ in 0..20000 {
        let inputs = target.resolve(state);
        let word = words[usize::from(state.pc)];
        let next = state.tick(word, inputs, false);
        assert_eq!(native_step(state, word, inputs, false), next);
        assert_eq!(ir_step(ir, state, word, inputs, false), next);
        let en = if target.drive.is_some() {
            target.mask()
        } else {
            0
        };
        let value = if target.drive == Some(true) {
            target.mask()
        } else {
            0
        };
        assert_eq!(next.enables & en, 0, "handoff before target release");
        hdl.push_pull_edge(value, en, inputs, target.mask(), next);
        target.advance(next);
        state = next;
        if state.halted {
            break;
        }
    }
    assert!(state.halted && !state.fault, "{case:?} {state:?}");
    assert_eq!(state.pins & (1 << case.clock), 0);
    assert_ne!(state.pins & target.mask(), 0);
    assert_eq!(target.phase, Phase::Idle);
    let exhausted = case.waits >= usize::from(case.attempts) || case.ack == 2;
    let expected = if exhausted {
        (1 << 9) | (1 << 10)
    } else if case.ack == 4 {
        (1 << 9) | (1 << 11)
    } else if case.ack != 1 {
        (1 << 9) | (1 << 13)
    } else if case.read && case.bad_parity {
        (1 << 9) | (1 << 12)
    } else {
        1 << 8
    };
    assert_eq!(state.scratch & (63 << 8), expected, "{case:?}");
    assert_eq!(
        target.requests,
        if exhausted {
            usize::from(case.attempts)
        } else {
            case.waits + 1
        }
    );
    if case.ack == 1 && !exhausted {
        if case.read {
            assert_eq!((state.scratch >> 32) as u32, case.value);
        } else {
            assert_eq!(target.writes, [case.value]);
        }
    }
}

#[test]
fn swd_wire_requests_responses_turnaround_parity_and_retries() {
    let ir = processor_step::ir().unwrap();
    let mut hdl = ClockedVectors::new();
    let base = Case {
        read: true,
        ap: false,
        address: 0,
        value: 0xa569963c,
        waits: 0,
        ack: 1,
        bad_parity: false,
        attempts: 3,
        hold: 1,
        clock: 0,
        data: 1,
    };
    let mut cases = 0;
    for byte in 0..=255_u32 {
        for read in [false, true] {
            check(
                Case {
                    read,
                    ap: byte % 2 == 1,
                    address: ((byte / 2) % 4 * 4) as u8,
                    value: 0x96a56900 | byte,
                    ..base
                },
                &ir,
                &mut hdl,
            );
            cases += 1;
        }
    }
    for read in [false, true] {
        for value in [0, u32::MAX, 1, 0x80000000, 0x5aa59669] {
            check(
                Case {
                    read,
                    value,
                    waits: 2,
                    clock: 6,
                    data: 7,
                    hold: 3,
                    ..base
                },
                &ir,
                &mut hdl,
            );
            cases += 1;
        }
        for ack in 0..8 {
            check(Case { read, ack, ..base }, &ir, &mut hdl);
            cases += 1;
        }
        for (waits, attempts) in [(0, 1), (1, 1), (1, 2), (2, 2), (2, 3)] {
            check(
                Case {
                    read,
                    waits,
                    attempts,
                    ..base
                },
                &ir,
                &mut hdl,
            );
            cases += 1;
        }
    }
    check(
        Case {
            bad_parity: true,
            ..base
        },
        &ir,
        &mut hdl,
    );
    cases += 1;
    println!("{cases} independent resolved push-pull SWD scenarios");
    hdl.finish();
}

#[test]
fn swd_reset_parameters_and_atomic_sample_contract() {
    let cfg = Config {
        clock: Pin::new(0).unwrap(),
        data: Pin::new(1).unwrap(),
        hold: 1,
        attempts: 3,
        retry_gap: 0,
    };
    let read = swd::transaction(false, 0, Transfer::Read, cfg).unwrap();
    println!("SWD read image: {} words", read.instructions().len());
    for address in 0..=255 {
        assert_eq!(
            swd::transaction(false, address, Transfer::Read, cfg).is_ok(),
            matches!(address, 0 | 4 | 8 | 12)
        );
    }
    for invalid in [
        Config {
            clock: cfg.data,
            ..cfg
        },
        Config { hold: 0, ..cfg },
        Config { attempts: 0, ..cfg },
    ] {
        assert!(swd::line_reset(invalid).is_err());
    }
    let ir = processor_step::ir().unwrap();
    let mut hdl = ClockedVectors::new();
    let words = swd::line_reset(cfg).unwrap().words();
    hdl.load(&words);
    let mut state = State::default();
    hdl.edge(true, 0, state);
    let mut bits = vec![];
    for _ in 0..2000 {
        let inputs = !(state.enables & !state.pins);
        let next = state.tick(words[usize::from(state.pc)], inputs, false);
        if state.pins & 1 == 0 && next.pins & 1 != 0 {
            bits.push(next.pins & 2 != 0);
        }
        hdl.push_pull_edge(0, 0, inputs, 2, next);
        state = next;
        if state.halted {
            break;
        }
    }
    assert_eq!(bits, [vec![true; 56], vec![false; 2]].concat());
    assert!(state.halted && !state.fault);
    let sample = Instruction::SampleAndSet {
        dst: Register::new(0).unwrap(),
        pin: Pin::new(0).unwrap(),
        mask: 1,
        value: 1,
    };
    let code = Program::new(vec![
        Instruction::ConfigurePins {
            mask: 1,
            enables: 1,
            value: 0,
        },
        sample,
        Instruction::Halt,
    ])
    .unwrap();
    let words = code.words();
    hdl.load(&words);
    state = State::default();
    hdl.edge(true, 0, state);
    for word in words {
        let inputs = !(state.enables & !state.pins);
        let next = state.tick(word, inputs, false);
        assert_eq!(native_step(state, word, inputs, false), next);
        assert_eq!(ir_step(&ir, state, word, inputs, false), next);
        hdl.push_pull_edge(0, 0, inputs, 1, next);
        state = next;
    }
    assert_eq!(state.scratch & 1, 0);
    assert_eq!(state.pins, 1);
    hdl.finish();
    assert!(Instruction::decode(0xc2000000).is_err());
    assert!(Instruction::decode(0xd0000001).is_err());
    let sample = Instruction::SampleAndSet {
        dst: Register::new(63).unwrap(),
        pin: Pin::new(7).unwrap(),
        mask: 0x81,
        value: 255,
    };
    assert_eq!(sample.encode(), 0xc10303ff);
    assert_eq!(
        Instruction::decode(0xc10303ff).unwrap(),
        Instruction::SampleAndSet {
            dst: Register::new(63).unwrap(),
            pin: Pin::new(7).unwrap(),
            mask: 0x81,
            value: 0x81
        }
    );
    assert_eq!(
        Instruction::ParityWord(Register::new(63).unwrap()).encode(),
        0xd03f0000
    );
    for dst in 0..64 {
        let instruction = Instruction::ParityWord(Register::new(dst).unwrap());
        assert_eq!(
            Instruction::decode(instruction.encode()).unwrap(),
            instruction
        );
        for value in [0, u32::MAX, 1, 0x80000000, 0xa5965a69] {
            let before = State {
                scratch: (u64::from(value) << 32) | 0x1234,
                ..State::default()
            };
            let next = before.tick(instruction.encode(), 0, false);
            assert_eq!(
                (next.scratch >> dst) & 1,
                u64::from(!value.count_ones().is_multiple_of(2))
            );
            assert_eq!(next.scratch & !(1 << dst), before.scratch & !(1 << dst));
        }
    }
}
