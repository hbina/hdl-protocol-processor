use super::*;
use crate::{
    composition::{Composer, Handoff, Operation},
    protocols::{poll, spi},
};

fn uart_operation(pin: u8) -> Operation {
    Operation::single_exit(
        "uart",
        uart::transmit(b"A", Pin::new(pin).unwrap(), 2).unwrap(),
    )
    .unwrap()
}

#[test]
fn composed_uart_spi_timing_results_and_shared_handoff() {
    let ir = processor_step::ir().unwrap();
    let mut hdl = ClockedVectors::new();
    let mut cases = 0;
    for shared in [false, true] {
        for mode in 0..4 {
            for period in [1, 2, 8] {
                let mut composer = Composer::default();
                composer
                    .push(
                        Operation::single_exit(
                            "uart",
                            uart::transmit(b"A", Pin::new(0).unwrap(), period).unwrap(),
                        )
                        .unwrap(),
                        None,
                    )
                    .unwrap();
                let clock = if shared { 0 } else { 1 };
                let h = 2_usize;
                let cfg = spi::Config {
                    clock: Pin::new(clock).unwrap(),
                    mosi: Pin::new(2).unwrap(),
                    miso: Pin::new(3).unwrap(),
                    select: Pin::new(4).unwrap(),
                    mode,
                    lsb_first: false,
                    half_period: h as u32,
                };
                let handoff = if shared {
                    Some(Handoff {
                        release: 1,
                        clocks: 3,
                    })
                } else {
                    None
                };
                composer
                    .push(
                        Operation::single_exit("spi", spi::transfer(0x69, cfg).unwrap()).unwrap(),
                        handoff,
                    )
                    .unwrap();
                let combined = composer.finish().unwrap();
                assert_eq!(combined.locations[0].entry, 0);
                let words = combined.program.words();
                let mut state = State::default();
                hdl.load(&words);
                hdl.edge(true, 0, state);
                let uart_end = 11 * period as usize;
                let spi_start = uart_end + 1 + if shared { 4 } else { 0 };
                let deselect = 1 + 17 * h;
                let mut expected_result = 0;
                for edge in 0..=spi_start + deselect + 1 {
                    let local = edge.saturating_sub(spi_start);
                    let first_setup = if mode % 2 == 0 { 1 } else { 1 + h };
                    let incoming = edge >= spi_start
                        && local >= first_setup
                        && 0x96_u8 & (1 << (7 - ((local - first_setup) / (2 * h)).min(7))) != 0;
                    let inputs = if incoming { 8 } else { 0 };
                    let word = words[usize::from(state.pc)];
                    let next = state.tick(word, inputs, false);
                    assert_eq!(native_step(state, word, inputs, false), next);
                    assert_eq!(ir_step(&ir, state, word, inputs, false), next);
                    if edge < uart_end {
                        let symbols = uart_levels(b"A");
                        assert_eq!(next.pins & 1 != 0, symbols[edge / period as usize]);
                        assert_eq!(next.enables & 1, 1);
                    } else if edge < spi_start {
                        if shared && edge > uart_end {
                            assert_eq!(next.enables & 1, 0);
                            assert_eq!(next.pins & 1, 0);
                        } else {
                            assert_eq!(next.pins & 1, 1);
                            assert_eq!(next.enables & 1, 1);
                        }
                    }
                    if edge >= spi_start {
                        let active = local > h
                            && local < deselect
                            && ((local - 1 - h) / h).is_multiple_of(2);
                        assert_eq!(next.pins & (1 << clock) != 0, (mode >= 2) ^ active);
                        assert_eq!(next.pins & 16 != 0, local == 0 || local >= deselect);
                        assert_eq!(next.enables & 8, 0);
                        if !shared {
                            assert_eq!(next.pins & 1, 1);
                        }
                        for n in 0..8 {
                            let sample = 1 + h + 2 * n * h + if mode % 2 == 0 { 0 } else { h };
                            if local == sample {
                                assert_eq!(next.pins & 4 != 0, 0x69_u8 & (1 << (7 - n)) != 0);
                            }
                            if local == sample + 1 && 0x96_u8 & (1 << (7 - n)) != 0 {
                                expected_result |= 1_u64 << (32 + 7 - n);
                            }
                        }
                    }
                    assert_eq!(next.scratch, expected_result);
                    assert_eq!(next.halted, edge == spi_start + deselect + 1);
                    assert!(!next.fault);
                    hdl.edge(false, inputs, next);
                    state = next;
                }
                assert_eq!(state.scratch >> 32, 0x96);
                cases += 1;
            }
        }
    }
    println!("{cases} independent composed UART/SPI waveforms");
    hdl.finish();
}

#[test]
fn conditional_success_exits_preserve_errors() {
    let ir = processor_step::ir().unwrap();
    let mut hdl = ClockedVectors::new();
    for ready in [false, true] {
        let mut c = Composer::default();
        let program = poll::input_high(Pin::new(0).unwrap(), 3, 1).unwrap();
        c.push(Operation::new("poll", program, vec![8]).unwrap(), None)
            .unwrap();
        c.push(
            Operation::single_exit(
                "uart",
                uart::transmit(b"", Pin::new(7).unwrap(), 2).unwrap(),
            )
            .unwrap(),
            Some(Handoff {
                release: 128,
                clocks: 1,
            }),
        )
        .unwrap();
        let composition = c.finish().unwrap();
        let words = composition.program.words();
        let mut state = State::default();
        hdl.load(&words);
        hdl.edge(true, 0, state);
        let expected_cycles = if ready { 10 } else { 15 };
        for edge in 0..expected_cycles {
            let inputs = u8::from(ready);
            let word = words[usize::from(state.pc)];
            let next = state.tick(word, inputs, false);
            assert_eq!(native_step(state, word, inputs, false), next);
            assert_eq!(ir_step(&ir, state, word, inputs, false), next);
            assert_eq!(next.halted, edge + 1 == expected_cycles);
            hdl.edge(false, inputs, next);
            state = next;
        }
        assert_eq!(state.scratch >> 62, if ready { 1 } else { 2 });
        assert_eq!(state.enables & 128, if ready { 128 } else { 0 });
    }
    hdl.finish();
}

#[test]
fn composition_rejects_resources_exits_capacity_and_relocates_branches() {
    assert!(
        Operation::new(
            "bad",
            Program::new(vec![wait(1), Instruction::Halt]).unwrap(),
            vec![0]
        )
        .is_err()
    );
    assert!(
        Operation::new(
            "bad",
            Program::new(vec![Instruction::Halt]).unwrap(),
            vec![0, 0]
        )
        .is_err()
    );
    assert!(
        Operation::single_exit(
            "bad",
            Program::new(vec![Instruction::Halt, Instruction::Halt]).unwrap()
        )
        .is_err()
    );
    let mut c = Composer::default();
    assert!(
        c.push(
            uart_operation(0),
            Some(Handoff {
                release: 1,
                clocks: 1
            })
        )
        .is_err()
    );
    c.push(uart_operation(0), None).unwrap();
    assert!(c.push(uart_operation(0), None).is_err());
    assert!(
        c.push(
            uart_operation(1),
            Some(Handoff {
                release: 128,
                clocks: 1
            })
        )
        .is_err()
    );
    c.push(uart_operation(1), None).unwrap();
    assert_eq!(c.finish().unwrap().locations.len(), 2);
    let mut c = Composer::default();
    let mut code = vec![wait(1); 254];
    code.push(Instruction::Halt);
    c.push(
        Operation::single_exit("full", Program::new(code).unwrap()).unwrap(),
        None,
    )
    .unwrap();
    c.push(
        Operation::single_exit("last", Program::new(vec![Instruction::Halt]).unwrap()).unwrap(),
        None,
    )
    .unwrap();
    assert!(
        c.push(
            Operation::single_exit("overflow", Program::new(vec![Instruction::Halt]).unwrap())
                .unwrap(),
            None
        )
        .is_err()
    );
    let full = c.finish().unwrap();
    assert_eq!(full.program.words().len(), 256);
    let (outcome, trace) = run(&full.program, 257);
    assert_eq!(outcome, Outcome::Halted);
    assert_eq!(trace.len(), 256);
    assert_eq!(trace.last().unwrap().pc, 255);
    let mut c = Composer::default();
    c.push(
        Operation::single_exit(
            "first",
            Program::new(vec![wait(1), Instruction::Halt]).unwrap(),
        )
        .unwrap(),
        None,
    )
    .unwrap();
    c.push(
        Operation::single_exit(
            "loop",
            Program::new(vec![
                Instruction::LoadCount(3),
                Instruction::DecJump(1),
                Instruction::Halt,
            ])
            .unwrap(),
        )
        .unwrap(),
        None,
    )
    .unwrap();
    let result = c.finish().unwrap();
    assert_eq!(result.program.words()[3], 0x90000003);
    assert_eq!(run(&result.program, 8).1.len(), 7);
    let mut c = Composer::default();
    c.push(
        Operation::single_exit("first", Program::new(vec![Instruction::Halt]).unwrap()).unwrap(),
        None,
    )
    .unwrap();
    c.push(
        Operation::new(
            "branch",
            Program::new(vec![
                Instruction::Jump(2),
                Instruction::Halt,
                Instruction::BranchBit {
                    src: Register::new(0).unwrap(),
                    value: false,
                    target: 4,
                },
                Instruction::Halt,
                Instruction::Halt,
            ])
            .unwrap(),
            vec![4],
        )
        .unwrap(),
        None,
    )
    .unwrap();
    let words = c.finish().unwrap().program.words();
    assert_eq!(words[1], 0x60000003);
    assert_eq!(words[3], 0x70000005);
}
