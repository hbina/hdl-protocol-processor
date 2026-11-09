use super::*;
use crate::protocols::jtag::{self, Config, RegisterKind};

// Table from the sixteen-state TAP diagram, independent of builder TMS paths.
const NEXT: [[usize; 2]; 16] = [
    [1, 0],
    [1, 2],
    [3, 9],
    [4, 5],
    [4, 5],
    [6, 8],
    [6, 7],
    [4, 8],
    [1, 2],
    [10, 0],
    [11, 12],
    [11, 12],
    [13, 15],
    [13, 14],
    [11, 15],
    [1, 2],
];

struct Tap {
    state: usize,
    clock: bool,
    tdo: bool,
    shift: u32,
    capture: u32,
    width: u8,
    updated: Vec<(RegisterKind, u32)>,
    shifts: usize,
    visited_reset: bool,
}
impl Tap {
    fn advance(&mut self, pins: u8) {
        let clock = pins & 1 != 0;
        if !self.clock && clock {
            match self.state {
                0 => {
                    self.visited_reset = true;
                    self.shifts = 0;
                    self.updated.clear();
                }
                3 | 10 => self.shift = self.capture,
                4 | 11 => {
                    self.shift = (self.shift >> 1) | (u32::from(pins & 4 != 0) << (self.width - 1));
                    self.shifts += 1;
                }
                8 => self.updated.push((RegisterKind::Data, self.shift)),
                15 => self.updated.push((RegisterKind::Instruction, self.shift)),
                _ => {}
            }
            self.state = NEXT[self.state][usize::from(pins & 2 != 0)];
        }
        if self.clock && !clock {
            self.tdo = matches!(self.state, 4 | 11) && self.shift & 1 != 0;
        }
        self.clock = clock;
    }
}

fn check_scan(
    kind: RegisterKind,
    value: u32,
    width: u8,
    initial: usize,
    hold: u16,
    ir: &bitlogic::Logic,
    hdl: &mut ClockedVectors,
) {
    let cfg = Config {
        tck: Pin::new(0).unwrap(),
        tms: Pin::new(1).unwrap(),
        tdi: Pin::new(2).unwrap(),
        tdo: Pin::new(3).unwrap(),
        hold,
    };
    let words = jtag::scan(kind, value, width, cfg).unwrap().words();
    let mask = u32::MAX >> (32 - width);
    let capture = 0x96a5693c & mask;
    let mut tap = Tap {
        state: initial,
        clock: false,
        tdo: false,
        shift: 0,
        capture,
        width,
        updated: vec![],
        shifts: 0,
        visited_reset: false,
    };
    let mut state = State::default();
    hdl.load(&words);
    hdl.edge(true, 0, state);
    for _ in 0..10000 {
        let inputs = if tap.tdo { 8 } else { 0 };
        let next = state.tick(words[usize::from(state.pc)], inputs, false);
        assert_eq!(
            native_step(state, words[usize::from(state.pc)], inputs, false),
            next
        );
        assert_eq!(
            ir_step(ir, state, words[usize::from(state.pc)], inputs, false),
            next
        );
        assert_eq!(next.enables, 7);
        assert_eq!(next.pins & !7, 0);
        // TDI/TMS must remain stable throughout a high TCK interval.
        if state.pins & 1 != 0 && next.pins & 1 != 0 {
            assert_eq!(state.pins & 6, next.pins & 6);
        }
        hdl.edge(false, inputs, next);
        tap.advance(next.pins);
        state = next;
        if state.halted {
            break;
        }
    }
    assert!(state.halted && !state.fault);
    assert!(tap.visited_reset);
    assert_eq!(tap.state, 1);
    assert_eq!(tap.shifts, usize::from(width));
    assert_eq!(tap.updated, [(kind, value)]);
    assert_eq!(state.scratch as u32 & mask, capture);
    assert_eq!(state.pins & 3, 0);
}

#[test]
fn jtag_reset_scan_and_capture_against_tap() {
    let ir = processor_ir().unwrap();
    let mut hdl = ClockedVectors::new();
    let mut cases = 0;
    for kind in [RegisterKind::Data, RegisterKind::Instruction] {
        for initial in 0..16 {
            for width in [1, 4, 8, 16, 32] {
                check_scan(
                    kind,
                    0xa569963c & (u32::MAX >> (32 - width)),
                    width,
                    initial,
                    1,
                    &ir,
                    &mut hdl,
                );
                cases += 1;
            }
        }
        for byte in 0..=255 {
            check_scan(kind, byte, 8, 0, 2, &ir, &mut hdl);
            cases += 1;
        }
    }
    println!("{cases} independent JTAG TAP scenarios");
    hdl.finish();
}

#[test]
fn jtag_parameters_and_capacity() {
    let cfg = Config {
        tck: Pin::new(0).unwrap(),
        tms: Pin::new(1).unwrap(),
        tdi: Pin::new(2).unwrap(),
        tdo: Pin::new(3).unwrap(),
        hold: 1,
    };
    for width in [0, 33, 255] {
        assert!(jtag::scan(RegisterKind::Data, 0, width, cfg).is_err());
    }
    assert!(jtag::scan(RegisterKind::Data, 256, 8, cfg).is_err());
    assert!(jtag::scan(RegisterKind::Data, 0, 8, Config { hold: 0, ..cfg }).is_err());
    assert!(
        jtag::scan(
            RegisterKind::Data,
            0,
            8,
            Config {
                tdo: cfg.tdi,
                ..cfg
            }
        )
        .is_err()
    );
    assert_eq!(
        jtag::scan(RegisterKind::Instruction, u32::MAX, 32, cfg)
            .unwrap()
            .instructions()
            .len(),
        211
    );
}

#[test]
fn jtag_ir_then_dr_preserves_instruction_and_both_results() {
    use jtag::Scan;
    let cfg = Config {
        tck: Pin::new(0).unwrap(),
        tms: Pin::new(1).unwrap(),
        tdi: Pin::new(2).unwrap(),
        tdo: Pin::new(3).unwrap(),
        hold: 1,
    };
    let scans = [
        Scan {
            kind: RegisterKind::Instruction,
            value: 0xa,
            width: 4,
            capture: 0,
        },
        Scan {
            kind: RegisterKind::Data,
            value: 0x12345678,
            width: 32,
            capture: 32,
        },
    ];
    let program = jtag::sequence(&scans, cfg).unwrap();
    assert_eq!(program.instructions().len(), 251);
    let words = program.words();
    let ir = processor_ir().unwrap();
    let mut hdl = ClockedVectors::new();
    for initial in 0..16 {
        let mut tap = initial;
        let mut clock = false;
        let mut tdo = false;
        let mut instruction = 15_u32;
        let mut ir_shift = 0;
        let mut dr_shift = 0;
        let mut updated_data = None;
        let mut seen_reset = false;
        let mut state = State::default();
        hdl.load(&words);
        hdl.edge(true, 0, state);
        for _ in 0..2000 {
            let inputs = if tdo { 8 } else { 0 };
            let word = words[usize::from(state.pc)];
            let next = state.tick(word, inputs, false);
            assert_eq!(native_step(state, word, inputs, false), next);
            assert_eq!(ir_step(&ir, state, word, inputs, false), next);
            hdl.edge(false, inputs, next);
            let next_clock = next.pins & 1 != 0;
            if !clock && next_clock {
                match tap {
                    0 => {
                        seen_reset = true;
                        instruction = 15;
                        updated_data = None;
                    }
                    10 => ir_shift = 5,
                    11 => ir_shift = (ir_shift >> 1) | (u32::from(next.pins & 4 != 0) << 3),
                    15 => instruction = ir_shift,
                    3 => {
                        if seen_reset {
                            assert_eq!(instruction, 0xa, "IR must survive into DR capture");
                        }
                        dr_shift = 0xa5965aa5;
                    }
                    4 => dr_shift = (dr_shift >> 1) | (u32::from(next.pins & 4 != 0) << 31),
                    8 => updated_data = Some(dr_shift),
                    _ => {}
                }
                tap = NEXT[tap][usize::from(next.pins & 2 != 0)];
            }
            if clock && !next_clock {
                tdo = match tap {
                    11 => ir_shift & 1 != 0,
                    4 => dr_shift & 1 != 0,
                    _ => false,
                };
            }
            clock = next_clock;
            state = next;
            if state.halted {
                break;
            }
        }
        assert!(state.halted && !state.fault);
        assert_eq!(tap, 1);
        assert_eq!(instruction, 0xa);
        assert_eq!(updated_data, Some(0x12345678));
        assert_eq!(state.scratch, 0xa5965aa500000005);
    }
    hdl.finish();
    assert!(jtag::sequence(&[], cfg).is_err());
    assert!(jtag::sequence(&[scans[0], scans[0]], cfg).is_err());
    assert!(
        jtag::sequence(
            &[Scan {
                capture: 63,
                ..scans[1]
            }],
            cfg
        )
        .is_err()
    );
    assert!(
        jtag::sequence(
            &[
                Scan {
                    width: 32,
                    value: u32::MAX,
                    ..scans[0]
                },
                scans[1]
            ],
            cfg
        )
        .is_err()
    );
}
