use super::*;
use crate::protocols::ps2::{self, Config};

#[derive(Clone, Copy)]
struct Case {
    byte: u8,
    clock: u8,
    data: u8,
    initial_inhibit: usize,
    inhibit_after: Option<usize>,
    request: bool,
    hold: u16,
}

fn check(case: Case, ir: &bitlogic::Logic, hdl: &mut ClockedVectors) {
    let cfg = Config {
        clock: Pin::new(case.clock).unwrap(),
        data: Pin::new(case.data).unwrap(),
        hold: case.hold,
        idle_hold: 4,
        attempts: 16,
    };
    let words = ps2::device_transmit(case.byte, cfg).unwrap().words();
    let clock = 1 << case.clock;
    let data = 1 << case.data;
    let bus = clock | data;
    let mut state = State::default();
    hdl.load(&words);
    hdl.edge(true, 0, state);
    let mut captured = Vec::new();
    let mut clock_low = false;
    let mut high_phase_data = None;
    for edge in 0..2000 {
        let inhibited = edge < case.initial_inhibit
            || case
                .inhibit_after
                .is_some_and(|count| captured.len() >= count);
        let external = if inhibited { clock } else { 0 } | if case.request { data } else { 0 };
        let inputs = !(state.enables & !state.pins | external);
        let word = words[usize::from(state.pc)];
        let next = state.tick(word, inputs, false);
        assert_eq!(native_step(state, word, inputs, false), next);
        assert_eq!(ir_step(ir, state, word, inputs, false), next);
        assert_eq!(next.pins & bus, 0);
        hdl.bus_edge(external, inputs, bus, false, next);
        let levels = !(next.enables & !next.pins | external);
        let next_low = levels & clock == 0;
        if !inhibited && !clock_low && next_low {
            captured.push(levels & data != 0);
            assert_eq!(
                high_phase_data,
                Some(levels & data != 0),
                "data changed at sample edge"
            );
        }
        if !next_low {
            high_phase_data = Some(levels & data != 0);
        }
        clock_low = next_low;
        state = next;
        if state.halted {
            break;
        }
    }
    assert!(state.halted && !state.fault);
    assert_eq!(state.enables & bus, 0);
    if case.initial_inhibit >= 1000 {
        assert_eq!(state.scratch >> 59, 17);
        assert!(captured.is_empty());
    } else if case.request {
        assert_eq!(state.scratch >> 59, 18);
        assert!(captured.is_empty());
    } else if let Some(count) = case.inhibit_after {
        assert_eq!(state.scratch >> 59, 20);
        assert_eq!(captured.len(), count);
    } else {
        assert_eq!(state.scratch >> 59, 8);
        assert_eq!(captured.len(), 11);
        assert!(!captured[0]);
        assert!(captured[10]);
        let received = captured[1..9]
            .iter()
            .enumerate()
            .fold(0, |acc, (bit, &high)| acc | (u8::from(high) << bit));
        assert_eq!(received, case.byte);
        assert_eq!(captured[1..10].iter().filter(|&&high| high).count() % 2, 1);
    }
}

#[test]
fn ps2_device_frames_inhibit_request_and_timeout() {
    let ir = processor_ir().unwrap();
    let mut hdl = ClockedVectors::new();
    let base = Case {
        byte: 0xa5,
        clock: 0,
        data: 1,
        initial_inhibit: 0,
        inhibit_after: None,
        request: false,
        hold: 1,
    };
    let mut cases = 0;
    for byte in 0..=255 {
        check(Case { byte, ..base }, &ir, &mut hdl);
        cases += 1;
    }
    for byte in [0, 0xff, 0xa5, 0x69] {
        check(
            Case {
                byte,
                clock: 6,
                data: 7,
                hold: 3,
                initial_inhibit: 12,
                ..base
            },
            &ir,
            &mut hdl,
        );
        cases += 1;
    }
    for count in 1..=10 {
        check(
            Case {
                inhibit_after: Some(count),
                ..base
            },
            &ir,
            &mut hdl,
        );
        cases += 1;
    }
    check(
        Case {
            initial_inhibit: 1000,
            ..base
        },
        &ir,
        &mut hdl,
    );
    cases += 1;
    check(
        Case {
            request: true,
            ..base
        },
        &ir,
        &mut hdl,
    );
    cases += 1;
    println!("{cases} independent resolved-bus PS/2 scenarios");
    hdl.finish();
}

#[test]
fn ps2_parameters() {
    let cfg = Config {
        clock: Pin::new(0).unwrap(),
        data: Pin::new(1).unwrap(),
        hold: 1,
        idle_hold: 4,
        attempts: 8,
    };
    for invalid in [
        Config {
            clock: cfg.data,
            ..cfg
        },
        Config { hold: 0, ..cfg },
        Config {
            idle_hold: 0,
            ..cfg
        },
        Config { attempts: 0, ..cfg },
    ] {
        assert!(ps2::device_transmit(0, invalid).is_err());
    }
}
