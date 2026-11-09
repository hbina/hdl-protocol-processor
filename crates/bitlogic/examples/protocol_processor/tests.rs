use super::{core::processor_ir, isa::*, protocols::uart, reference::State, runner::*};
use std::{
    fmt::Write as _,
    io::{BufWriter, Write},
    num::NonZeroU16,
    path::Path,
    process::Command,
};
mod composition;
mod i2c;
mod jtag;
mod ps2;
mod swd;
mod uart_batch;

fn wait(cycles: u16) -> Instruction {
    Instruction::Wait(NonZeroU16::new(cycles).unwrap())
}

fn packed(state: State) -> u128 {
    u128::from(state.pc)
        | (u128::from(state.wait) << 8)
        | (u128::from(state.pins) << 24)
        | (u128::from(state.halted) << 32)
        | (u128::from(state.fault) << 33)
        | (u128::from(state.scratch) << 34)
        | (u128::from(state.count) << 98)
        | (u128::from(state.enables) << 114)
}

fn execute_hdl(dir: &Path, source: &str) {
    std::fs::write(dir.join("test.v"), source).unwrap();
    let mut compiler = Command::new("iverilog");
    compiler
        .current_dir(dir)
        .args(["-g2012", "-s", "tb", "-o", "test.vvp", "test.v"]);
    if let Some(models) = std::env::var_os("BITLOGIC_PROCESSOR_CELL_MODELS") {
        compiler.arg(models);
    }
    let compiled = compiler.output().expect("Icarus Verilog is required");
    assert!(
        compiled.status.success(),
        "{}",
        String::from_utf8_lossy(&compiled.stderr)
    );
    let ran = Command::new("vvp")
        .current_dir(dir)
        .arg("test.vvp")
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&ran.stdout);
    assert!(
        ran.status.success() && stdout.contains("PROCESSOR PASS"),
        "{stdout}\n{}",
        String::from_utf8_lossy(&ran.stderr)
    );
}

fn processor_hdl() -> String {
    if let Some(path) = std::env::var_os("BITLOGIC_PROCESSOR_NETLIST") {
        std::fs::read_to_string(path).expect("read explicitly selected mapped netlist")
    } else {
        processor_ir()
            .unwrap()
            .to_verilog("processor_step")
            .unwrap()
    }
}

#[test]
fn checked_isa_encodings_and_image_limits() {
    assert_eq!(Instruction::Halt.encode(), 0xf0000000);
    assert_eq!(
        Instruction::SetPins {
            mask: 0x81,
            value: 0xff
        }
        .encode(),
        0x10008181
    );
    for cycles in 1..=u16::MAX {
        let word = 0x20000000 + u32::from(cycles);
        assert_eq!(wait(cycles).encode(), word);
        assert_eq!(Instruction::decode(word).unwrap(), wait(cycles));
    }
    for mask in 0..=u8::MAX {
        for value in 0..=u8::MAX {
            let word = Instruction::SetPins { mask, value }.encode();
            assert_eq!(
                word,
                0x10000000 + u32::from(mask) * 256 + u32::from(value & mask)
            );
            assert_eq!(Instruction::decode(word).unwrap().encode(), word);
        }
    }
    for word in [
        0,
        0x20000000,
        0x10010000,
        0x20010000,
        0xf0000001,
        0x30400000,
        u32::MAX,
    ] {
        assert!(Instruction::decode(word).is_err(), "{word:08x}");
    }
    for opcode in [0x10000000, 0x20000001, 0xf0000000] {
        let reserved = if opcode == 0xf0000000 { 0..28 } else { 16..28 };
        for bit in reserved {
            assert!(Instruction::decode(opcode | (1 << bit)).is_err());
        }
    }
    assert!(Pin::new(7).is_ok());
    for pin in 8..=255 {
        assert!(Pin::new(pin).is_err());
    }
    assert!(Program::new(vec![]).is_err());
    assert!(Program::new(vec![wait(1)]).is_err());
    assert!(Program::new(vec![Instruction::Halt, Instruction::Halt]).is_ok());
    let mut code = vec![wait(1); 255];
    code.push(Instruction::Halt);
    assert!(Program::new(code.clone()).is_ok());
    code.insert(0, wait(1));
    assert!(Program::new(code).is_err());
}

fn transition_cases(mut check: impl FnMut(State, u32, u8)) {
    let baseline = State {
        pc: 17,
        pins: 0xa5,
        ..State::default()
    };
    for duration in 1..=u16::MAX {
        check(baseline, 0x20000000 | u32::from(duration), 0);
        check(
            State {
                wait: duration,
                ..baseline
            },
            0,
            0xff,
        );
    }
    for mask in 0..=u8::MAX {
        for value in 0..=u8::MAX {
            // Raw, noncanonical words are valid too: out-of-mask values are ignored.
            check(
                baseline,
                0x10000000 | (u32::from(mask) << 8) | u32::from(value),
                0,
            );
        }
    }
    let words = [
        0,
        0x1000ff00,
        0x100000ff,
        0x20000001,
        0x2000ffff,
        0x20000000,
        0x10010000,
        0x20010000,
        0xf0000000,
        0xf0000001,
        u32::MAX,
    ];
    for pc in [0, 1, 254, 255] {
        for wait in [0, 1, 2, 65535] {
            for halted in [false, true] {
                for fault in [false, true] {
                    for word in words {
                        check(
                            State {
                                pc,
                                wait,
                                pins: 0x96,
                                halted,
                                fault,
                                scratch: 0x96a55aa5695aa596,
                                count: 7,
                                enables: 0x3c,
                            },
                            word,
                            0x69,
                        );
                    }
                }
            }
        }
    }
    for opcode in [0x10000000, 0x20000001, 0xf0000000] {
        for bit in 0..28 {
            check(baseline, opcode | (1 << bit), 0xff);
        }
    }
    for input in 0..=255 {
        check(
            State {
                scratch: u64::MAX,
                ..baseline
            },
            0x40000000,
            input,
        );
    }
    for dst in 0..64 {
        for lhs in [0, 1, 31, 32, 63, dst] {
            for rhs in [0, 63, dst] {
                for table in 0..16 {
                    for scratch in [0, u64::MAX, 0xa5965aa569a5a569] {
                        check(
                            State {
                                scratch,
                                ..baseline
                            },
                            0x30000000 | (dst << 16) | (lhs << 10) | (rhs << 4) | table,
                            0,
                        );
                    }
                }
            }
        }
    }
    for src in 0..64 {
        for pin in 0..8 {
            for scratch in [0, u64::MAX, 0xa5965aa569a5a569] {
                check(
                    State {
                        scratch,
                        ..baseline
                    },
                    0x50000000 | (src << 3) | pin,
                    0,
                );
            }
        }
    }
    for word in [0x30000000, 0x40000000, 0x50000000] {
        for bit in 0..28 {
            check(
                State {
                    scratch: u64::MAX,
                    ..baseline
                },
                word | (1 << bit),
                0xa5,
            );
        }
        check(
            State {
                pc: 255,
                scratch: u64::MAX,
                ..baseline
            },
            word,
            0xa5,
        );
    }
    for pc in [0, 254, 255] {
        for count in [0, 1, 2, 65535] {
            for scratch in [0, 1, 1 << 63, u64::MAX] {
                for word in [
                    0x60000000, 0x600000ff, 0x70000000, 0x700040ff, 0x70003fff, 0x70007f00,
                    0x80000000, 0x8000ffff, 0x90000000, 0x900000ff,
                ] {
                    check(
                        State {
                            pc,
                            count,
                            scratch,
                            ..baseline
                        },
                        word,
                        0,
                    );
                }
            }
        }
    }
    for word in [0x60000000, 0x70000000, 0x80000000, 0x90000000] {
        for bit in 0..28 {
            check(baseline, word | (1 << bit), 0);
        }
    }
    for dst in 0..64 {
        for pin in 0..8 {
            for inputs in [0, 255, 0xa5, 0x5a] {
                check(
                    State {
                        scratch: 0xa5a569965a5a9669,
                        ..baseline
                    },
                    0xa0000000 | (dst << 3) | pin,
                    inputs,
                );
            }
        }
    }
    for bit in 9..28 {
        check(baseline, 0xa0000000 | (1 << bit), 0xff);
    }
    for mask in 0..=255_u32 {
        for enables in 0..=255_u32 {
            check(
                State {
                    enables: 0x96,
                    ..baseline
                },
                0xb0000000 | (mask << 16) | (enables << 8) | (enables as u8).reverse_bits() as u32,
                0,
            );
        }
    }
    for bit in 24..28 {
        check(baseline, 0xb0000000 | (1 << bit), 0);
    }
    for pc in [254, 255] {
        for wait in [0, 1] {
            for halted in [false, true] {
                check(
                    State {
                        pc,
                        wait,
                        halted,
                        enables: 0xa5,
                        ..baseline
                    },
                    0xb0ffff69,
                    0,
                );
            }
        }
    }
    for dst in 0..64_u32 {
        for pin in 0..8_u32 {
            for inputs in [0, 0xff, 0x69, 0x96] {
                check(
                    State {
                        scratch: 0xa569965aa596695a,
                        enables: 0xff,
                        ..baseline
                    },
                    0xc0000000 | (0xa5 << 17) | (0x69 << 9) | (dst << 3) | pin,
                    inputs,
                );
            }
        }
        for word in [0, 1, u32::MAX, 0xa569963c]
            .into_iter()
            .chain((0..32).map(|bit| 1 << bit))
        {
            check(
                State {
                    scratch: (u64::from(word) << 32) | 0x6996a55a,
                    ..baseline
                },
                0xd0000000 | (dst << 16),
                0,
            );
        }
    }
    for word in [0xc0000000, 0xd0000000] {
        for bit in 0..28 {
            check(baseline, word | (1 << bit), 0xa5);
        }
        check(
            State {
                pc: 255,
                ..baseline
            },
            word,
            0xa5,
        );
        check(
            State {
                wait: 1,
                ..baseline
            },
            word,
            0xa5,
        );
        check(
            State {
                halted: true,
                ..baseline
            },
            word,
            0xa5,
        );
    }
}

#[test]
fn spi_modes_orders_waveforms_and_receive_results() {
    use super::protocols::spi;
    let ir = processor_ir().unwrap();
    let mut hdl = ClockedVectors::new();
    let mut programs = 0;
    for byte in 0..=255_u8 {
        for mode in 0..4 {
            for lsb_first in [false, true] {
                for half_period in if byte < 4 { vec![2, 3, 8] } else { vec![2] } {
                    let rx = byte.reverse_bits() ^ 0x69;
                    let cfg = spi::Config {
                        clock: Pin::new(0).unwrap(),
                        mosi: Pin::new(1).unwrap(),
                        miso: Pin::new(2).unwrap(),
                        select: Pin::new(3).unwrap(),
                        mode,
                        lsb_first,
                        half_period,
                    };
                    let program = spi::transfer(byte, cfg).unwrap();
                    let words = program.words();
                    hdl.load(&words);
                    hdl.edge(true, 0, State::default());
                    let mut state = State::default();
                    let half = half_period as usize;
                    let first_leading = 1 + half;
                    let deselect = 1 + 17 * half;
                    let bit = |n: usize| if lsb_first { n } else { 7 - n };
                    let sample_edge = |n: usize| {
                        first_leading + 2 * n * half + if mode % 2 == 0 { 0 } else { half }
                    };
                    for edge in 0..=deselect + 1 {
                        // Independent peer changes MISO at setup edges and holds
                        // through the following processor sampling edge.
                        let first_setup = if mode % 2 == 0 { 1 } else { first_leading };
                        let response_bit = if edge < first_setup {
                            false
                        } else {
                            rx & (1 << bit(((edge - first_setup) / (2 * half)).min(7))) != 0
                        };
                        let inputs = if response_bit { 4 } else { 0 };
                        let word = words[usize::from(state.pc)];
                        let next = state.tick(word, inputs, false);
                        assert_eq!(native_step(state, word, inputs, false), next);
                        assert_eq!(ir_step(&ir, state, word, inputs, false), next);
                        let idle = mode >= 2;
                        let active = edge >= first_leading
                            && edge < deselect
                            && ((edge - first_leading) / half).is_multiple_of(2);
                        let expected_clock = idle ^ active;
                        assert_eq!(
                            next.pins & 1 != 0,
                            expected_clock,
                            "mode={mode} edge={edge}"
                        );
                        assert_eq!(next.pins & 8 != 0, edge == 0 || edge >= deselect);
                        assert_eq!(next.pins & !0x0b, 0);
                        let mut expected_rx = 0_u64;
                        for n in 0..8 {
                            if edge == sample_edge(n) {
                                assert_eq!(next.pins & 2 != 0, byte & (1 << bit(n)) != 0);
                            }
                            if edge > sample_edge(n) && rx & (1 << bit(n)) != 0 {
                                expected_rx |= 1 << (32 + bit(n));
                            }
                        }
                        assert_eq!(next.scratch, expected_rx, "RX mode={mode} edge={edge}");
                        assert_eq!(next.halted, edge == deselect + 1);
                        assert!(!next.fault);
                        hdl.edge(false, inputs, next);
                        state = next;
                    }
                    assert_eq!((state.scratch >> 32) as u8, rx);
                    programs += 1;
                }
            }
        }
    }
    println!("{programs} independent SPI peer/waveform programs");
    hdl.finish();
}

#[test]
fn spi_parameters_and_sample_bit_contract() {
    use super::protocols::spi;
    let cfg = spi::Config {
        clock: Pin::new(0).unwrap(),
        mosi: Pin::new(1).unwrap(),
        miso: Pin::new(2).unwrap(),
        select: Pin::new(3).unwrap(),
        mode: 0,
        lsb_first: false,
        half_period: 2,
    };
    for half_period in [0, 1, 65537, u32::MAX] {
        assert!(spi::transfer(0, spi::Config { half_period, ..cfg }).is_err());
    }
    assert!(
        spi::transfer(
            0,
            spi::Config {
                half_period: 65536,
                ..cfg
            }
        )
        .is_ok()
    );
    assert!(spi::transfer(0, spi::Config { mode: 4, ..cfg }).is_err());
    assert!(
        spi::transfer(
            0,
            spi::Config {
                miso: cfg.mosi,
                ..cfg
            }
        )
        .is_err()
    );
    let instruction = Instruction::SampleBit {
        dst: Register::new(63).unwrap(),
        pin: Pin::new(7).unwrap(),
    };
    assert_eq!(instruction.encode(), 0xa00001ff);
    assert_eq!(
        Instruction::decode(instruction.encode()).unwrap(),
        instruction
    );
    assert!(Instruction::decode(0xa0000200).is_err());
    for inputs in [0, 128] {
        let initial = State {
            scratch: 0x123456789abcdef,
            ..State::default()
        };
        let next = initial.tick(instruction.encode(), inputs, false);
        assert_eq!(next.scratch & !(1 << 63), initial.scratch);
        assert_eq!(next.scratch >> 63, u64::from(inputs != 0));
    }
}

#[derive(Clone, Copy, Debug)]
struct RxCase {
    byte: u8,
    pin: u8,
    period: usize,
    start: Option<usize>,
    stop_high: bool,
    glitch: bool,
    back_to_back: bool,
}

fn check_receive(case: RxCase, ir: &bitlogic::Logic, hdl: &mut ClockedVectors) {
    let attempts = 16;
    let program = uart::receive(Pin::new(case.pin).unwrap(), case.period as u32, attempts).unwrap();
    let words = program.words();
    let mut state = State::default();
    hdl.load(&words);
    hdl.edge(true, 0, state);
    for edge in 0..(12 * case.period + 100) {
        let high = if let Some(start) = case.start {
            if edge < start {
                true
            } else if case.glitch {
                edge != start
            } else {
                let symbol = (edge - start) / case.period;
                match symbol {
                    0 => false,
                    1..=8 => case.byte & (1 << (symbol - 1)) != 0,
                    9 => case.stop_high,
                    10 if case.back_to_back => false,
                    _ => true,
                }
            }
        } else {
            true
        };
        let inputs = if high { 1 << case.pin } else { 0 };
        let word = words[usize::from(state.pc)];
        let next = state.tick(word, inputs, false);
        assert_eq!(native_step(state, word, inputs, false), next);
        assert_eq!(ir_step(ir, state, word, inputs, false), next);
        hdl.edge(false, inputs, next);
        state = next;
        if state.halted {
            break;
        }
    }
    assert!(state.halted && !state.fault, "{case:?} {state:?}");
    let expected_flags = if case.start.is_none() {
        0b1010
    } else if case.glitch {
        0b1001
    } else if !case.stop_high {
        0b1000
    } else {
        0b0100
    };
    assert_eq!(state.scratch >> 60, expected_flags, "{case:?}");
    if case.start.is_some() && !case.glitch {
        assert_eq!(
            (state.scratch >> 32) & 255,
            u64::from(case.byte),
            "{case:?}"
        );
    }
}

#[test]
fn uart_receive_bytes_phase_variation_and_errors() {
    let ir = processor_ir().unwrap();
    let mut hdl = ClockedVectors::new();
    let baseline = RxCase {
        byte: 0,
        pin: 0,
        period: 16,
        start: Some(10),
        stop_high: true,
        glitch: false,
        back_to_back: false,
    };
    let mut cases = 0;
    for byte in 0..=u8::MAX {
        for phase in 0..3 {
            check_receive(
                RxCase {
                    byte,
                    pin: if byte % 2 == 0 { 0 } else { 7 },
                    start: Some(10 + phase),
                    ..baseline
                },
                &ir,
                &mut hdl,
            );
            cases += 1;
        }
    }
    for period in [8, 32] {
        for phase in 0..3 {
            for byte in [0, 0xff, 0xa5, 0x69] {
                check_receive(
                    RxCase {
                        byte,
                        period,
                        start: Some(10 + phase),
                        back_to_back: true,
                        ..baseline
                    },
                    &ir,
                    &mut hdl,
                );
                cases += 1;
            }
        }
    }
    for byte in [0, 255, 0xa5] {
        check_receive(
            RxCase {
                byte,
                stop_high: false,
                ..baseline
            },
            &ir,
            &mut hdl,
        );
        cases += 1;
    }
    check_receive(
        RxCase {
            start: Some(10),
            glitch: true,
            ..baseline
        },
        &ir,
        &mut hdl,
    );
    cases += 1;
    check_receive(
        RxCase {
            start: None,
            ..baseline
        },
        &ir,
        &mut hdl,
    );
    cases += 1;
    println!("{cases} independent UART RX frames/error scenarios");
    hdl.finish();
    let pin = Pin::new(0).unwrap();
    for period in [0, 7, 9, 65537] {
        assert!(uart::receive(pin, period, 1).is_err());
    }
    assert!(uart::receive(pin, 8, 0).is_err());
    assert!(uart::receive(pin, 65536, 1).is_ok());
}

#[test]
fn control_flow_encodings_targets_and_polling() {
    use super::protocols::poll;
    for instruction in [
        Instruction::Jump(255),
        Instruction::BranchBit {
            src: Register::new(63).unwrap(),
            value: true,
            target: 255,
        },
        Instruction::LoadCount(65535),
        Instruction::DecJump(255),
    ] {
        assert_eq!(
            Instruction::decode(instruction.encode()).unwrap(),
            instruction
        );
    }
    assert_eq!(Instruction::Jump(255).encode(), 0x600000ff);
    assert_eq!(
        Instruction::BranchBit {
            src: Register::new(63).unwrap(),
            value: true,
            target: 255
        }
        .encode(),
        0x70007fff
    );
    for word in [0x60000100, 0x70008000, 0x80010000, 0x90000100] {
        assert!(Instruction::decode(word).is_err());
    }
    for instruction in [
        Instruction::Jump(2),
        Instruction::BranchBit {
            src: Register::new(0).unwrap(),
            value: false,
            target: 2,
        },
        Instruction::DecJump(2),
    ] {
        assert!(Program::new(vec![instruction, Instruction::Halt]).is_err());
    }
    let loop_forever = Program::new(vec![Instruction::Jump(0), Instruction::Halt]).unwrap();
    assert_eq!(run(&loop_forever, 100).0, Outcome::Limit);
    assert!(poll::input_high(Pin::new(0).unwrap(), 0, 1).is_err());
    assert!(poll::input_high(Pin::new(0).unwrap(), 1, 0).is_err());
    let ir = processor_ir().unwrap();
    let mut hdl = ClockedVectors::new();
    for pin in [0, 7] {
        for attempts in [1, 2, 5] {
            for gap in [1, 2, 8] {
                // Inputs change at every possible edge around all sample times.
                let timeout_cycles = 1 + usize::from(attempts) * (3 + usize::from(gap)) + 2;
                for high_at in 0..=timeout_cycles {
                    let program = poll::input_high(Pin::new(pin).unwrap(), attempts, gap).unwrap();
                    let words = program.words();
                    hdl.load(&words);
                    hdl.edge(true, 0, State::default());
                    let mut state = State::default();
                    let first_sample = (0..usize::from(attempts))
                        .map(|n| 1 + n * (3 + usize::from(gap)))
                        .find(|&edge| edge >= high_at);
                    let expected_cycles =
                        first_sample.map(|edge| edge + 4).unwrap_or(timeout_cycles);
                    for edge in 0..expected_cycles {
                        let inputs = if edge >= high_at { 1 << pin } else { 0 };
                        let word = words[usize::from(state.pc)];
                        let next = state.tick(word, inputs, false);
                        assert_eq!(native_step(state, word, inputs, false), next);
                        assert_eq!(ir_step(&ir, state, word, inputs, false), next);
                        hdl.edge(false, inputs, next);
                        state = next;
                        assert_eq!(state.halted, edge + 1 == expected_cycles);
                    }
                    assert_eq!(
                        state.scratch >> 62,
                        if first_sample.is_some() { 1 } else { 2 }
                    );
                    assert!(!state.fault);
                }
            }
        }
    }
    hdl.finish();
}

#[test]
fn scratch_operations_independent_expectations() {
    for index in 0..=255 {
        assert_eq!(Register::new(index).is_ok(), index < 64);
        assert_eq!(TruthTable::new(index).is_ok(), index < 16);
    }
    for table in 0..16 {
        for lhs in [false, true] {
            for rhs in [false, true] {
                let scratch = u64::from(lhs) | (u64::from(rhs) << 63);
                let mut set_bits = Vec::new();
                for bit in 0..4 {
                    set_bits.push(table & (1 << bit) != 0);
                }
                let expected = set_bits[usize::from(lhs) * 2 + usize::from(rhs)];
                for dst in [0, 31, 63] {
                    let instruction = Instruction::EvalBit {
                        dst: Register::new(dst).unwrap(),
                        lhs: Register::new(0).unwrap(),
                        rhs: Register::new(63).unwrap(),
                        table: TruthTable::new(table).unwrap(),
                    };
                    let word = instruction.encode();
                    assert_eq!(Instruction::decode(word).unwrap(), instruction);
                    let next = State {
                        scratch,
                        ..State::default()
                    }
                    .tick(word, 0, false);
                    assert_eq!((next.scratch >> dst) & 1, u64::from(expected));
                    assert_eq!(next.scratch & !(1 << dst), scratch & !(1 << dst));
                }
            }
        }
    }
    assert_eq!(Instruction::CaptureInputs.encode(), 0x40000000);
    assert_eq!(
        State {
            scratch: u64::MAX,
            ..State::default()
        }
        .tick(0x40000000, 0x69, false)
        .scratch,
        0x69
    );
    let instruction = Instruction::WriteBit {
        src: Register::new(63).unwrap(),
        pin: Pin::new(7).unwrap(),
    };
    assert_eq!(instruction.encode(), 0x500001ff);
    assert_eq!(Instruction::decode(0x500001ff).unwrap(), instruction);
    let next = State {
        scratch: 1 << 63,
        pins: 0x55,
        ..State::default()
    }
    .tick(0x500001ff, 0, false);
    assert_eq!(next.pins, 0xd5);
}

#[test]
fn native_ir_and_combinational_hdl_match_reference() {
    let ir = processor_ir().unwrap();
    let dir = tempfile::tempdir().unwrap();
    let mut vectors = BufWriter::new(std::fs::File::create(dir.path().join("vectors")).unwrap());
    let mut count = 0;
    transition_cases(|state, word, inputs| {
        let expected = state.tick(word, inputs, false);
        assert_eq!(
            native_step(state, word, inputs, false),
            expected,
            "{state:?} {word:08x}"
        );
        assert_eq!(ir_step(&ir, state, word, inputs, false), expected);
        writeln!(
            vectors,
            "{:x} {word:x} {inputs:x} {:x}",
            packed(state),
            packed(expected)
        )
        .unwrap();
        count += 1;
    });
    vectors.flush().unwrap();
    let mut source = processor_hdl();
    source.push_str(
        r#"
module tb;
reg [121:0] state; reg [31:0] instruction; reg [7:0] inputs;
wire [121:0] actual; reg [121:0] expected;
integer fd, rc, count;
processor_step dut(.i_pc(state[7:0]),.i_wait(state[23:8]),.i_pins(state[31:24]),
.i_halted(state[32]),.i_fault(state[33]),.i_instruction(instruction),.i_inputs(inputs),
.o_next_pc(actual[7:0]),.o_next_wait(actual[23:8]),.o_next_pins(actual[31:24]),
.o_next_halted(actual[32]),.o_next_fault(actual[33]),
.i_scratch(state[97:34]),.o_next_scratch(actual[97:34]),
.i_count(state[113:98]),.o_next_count(actual[113:98]),
.i_enables(state[121:114]),.o_next_enables(actual[121:114]));
initial begin
fd=$fopen("vectors","r"); if(!fd) $fatal(1,"missing vectors"); count=0;
while(!$feof(fd)) begin
rc=$fscanf(fd,"%h %h %h %h\n",state,instruction,inputs,expected);
if(rc!=4) $fatal(1,"bad vector");
#1; if(actual!==expected) $fatal(1,"transition %0d: got %h expected %h",count,actual,expected);
count=count+1;
end
"#,
    );
    writeln!(source, "if(count!={count}) $fatal(1,\"count\"); $display(\"PROCESSOR PASS: %0d transitions\",count); $finish; end endmodule").unwrap();
    execute_hdl(dir.path(), &source);
    println!("{count} independent reference/native/IR/combinational-HDL cases");
}

#[test]
fn wait_fault_reset_and_runner_contracts() {
    let mut state = State {
        pins: 0xa5,
        ..State::default()
    };
    state = state.tick(0x20000002, 0, false);
    assert_eq!(
        state,
        State {
            pc: 1,
            wait: 1,
            pins: 0xa5,
            ..State::default()
        }
    );
    state = state.tick(0, 0, false);
    assert_eq!(state.wait, 0);
    assert_eq!(state.pc, 1);
    state = state.tick(0x10000100, 0, false);
    assert_eq!((state.pc, state.pins), (2, 0xa4));
    state = state.tick(0x20000001, 0, false);
    assert_eq!((state.pc, state.wait), (3, 0));
    state = state.tick(0, 0, false);
    assert_eq!(
        state,
        State {
            pc: 3,
            pins: 0xa4,
            halted: true,
            fault: true,
            wait: 0,
            scratch: 0,
            count: 0,
            enables: 0
        }
    );
    assert_eq!(state.tick(0x1000ffff, 0, false), state);
    assert_eq!(state.tick(0, 0, true), State::default());
    let program = Program::new(vec![wait(2), Instruction::Halt]).unwrap();
    assert_eq!(run(&program, 0), (Outcome::Limit, vec![]));
    assert_eq!(run(&program, 2).0, Outcome::Limit);
    assert_eq!(run(&program, 3).0, Outcome::Halted);
}

// A waveform oracle expressed as serialized frame symbols, not instructions.
fn uart_levels(bytes: &[u8]) -> Vec<bool> {
    let mut symbols = vec![true];
    for byte in bytes {
        symbols.push(false);
        symbols.extend((0..8).map(|bit| (byte / 2_u8.pow(bit)) % 2 == 1));
        symbols.push(true);
    }
    symbols
}

struct ClockedVectors {
    dir: tempfile::TempDir,
    output: BufWriter<std::fs::File>,
    edges: usize,
}
impl ClockedVectors {
    fn new() -> Self {
        let dir = tempfile::tempdir().unwrap();
        let output = BufWriter::new(std::fs::File::create(dir.path().join("events")).unwrap());
        Self {
            dir,
            output,
            edges: 0,
        }
    }
    fn load(&mut self, words: &[u32]) {
        writeln!(self.output, "2 0 0 0 0 0").unwrap();
        for (address, word) in words.iter().enumerate() {
            writeln!(self.output, "1 {address:x} {word:x} 0 0 0").unwrap();
        }
    }
    fn edge(&mut self, reset: bool, inputs: u8, expected: State) {
        writeln!(
            self.output,
            "0 0 0 {:x} {inputs:x} {:x}",
            u8::from(reset),
            packed(expected)
        )
        .unwrap();
        self.edges += 1;
    }
    fn bus_edge(&mut self, peer_low: u8, inputs: u8, bus_mask: u8, reset: bool, expected: State) {
        let fields = u16::from(peer_low) | (u16::from(inputs) << 8);
        writeln!(
            self.output,
            "3 {bus_mask:x} 0 {:x} {fields:x} {:x}",
            u8::from(reset),
            packed(expected)
        )
        .unwrap();
        self.edges += 1;
    }
    fn push_pull_edge(
        &mut self,
        values: u8,
        enables: u8,
        inputs: u8,
        bus_mask: u8,
        expected: State,
    ) {
        let fields = u16::from(values) | (u16::from(inputs) << 8);
        writeln!(
            self.output,
            "4 {bus_mask:x} {enables:x} 0 {fields:x} {:x}",
            packed(expected)
        )
        .unwrap();
        self.edges += 1;
    }
    fn finish(mut self) {
        self.output.flush().unwrap();
        let clocked = std::env::var_os("BITLOGIC_PROCESSOR_CLOCKED_NETLIST");
        let mut source = if let Some(path) = &clocked {
            std::fs::read_to_string(path).expect("read selected clocked implementation")
        } else {
            processor_hdl()
        };
        if clocked.is_none() && std::env::var_os("BITLOGIC_PROCESSOR_NETLIST").is_none() {
            source.push_str(include_str!("hdl/processor_top.v"));
        }
        source.push_str(include_str!("hdl/pads.v"));
        source.push_str(
            r#"
module tb;
reg clk=0, reset; wire [7:0] inputs;
reg [7:0] direct_inputs,peer_enable,peer_value; reg bus_mode;
tri1 [7:0] bus; wire [7:0] bus_inputs;
protocol_pads pads(.values(pins),.enables(enables),.pads(bus),.inputs(bus_inputs));
genvar pin;
generate for(pin=0;pin<8;pin=pin+1) begin: peer
assign bus[pin]=peer_enable[pin] ? peer_value[pin] : 1'bz;
end endgenerate
assign inputs=bus_mode ? bus_inputs : direct_inputs;
wire [7:0] pc,pins,enables; wire [15:0] wait_remaining; wire halted,fault; wire [63:0] scratch; wire [15:0] count;
reg [31:0] rom[0:255]; wire [31:0] instruction=rom[pc];
wire [121:0] actual={enables,count,scratch,fault,halted,pins,wait_remaining,pc};
reg [121:0] expected; integer fd,rc,command,address,word,rst,inp,j,edge_count;
protocol_processor dut(.*);
initial begin
fd=$fopen("events","r"); if(!fd) $fatal(1,"missing events"); edge_count=0;
while(!$feof(fd)) begin
rc=$fscanf(fd,"%h %h %h %h %h %h\n",command,address,word,rst,inp,expected);
if(rc!=6) $fatal(1,"bad event");
if(command==2) begin for(j=0;j<256;j=j+1) rom[j]=0; end
else if(command==1) rom[address]=word;
else if(command==0 || command==3 || command==4) begin
reset=rst; bus_mode=(command>=3); direct_inputs=inp;
peer_enable=(command==4) ? word : inp; peer_value=(command==4) ? inp : 0;
#2;
if(command>=3 && inputs!==((inp>>8)&255)) $fatal(1,"resolved input mismatch %0d got %h",edge_count,inputs);
if(command==4 && ((peer_enable & enables & address)!=0)) $fatal(1,"ownership overlap before edge %0d",edge_count);
clk=1; #2;
if(command==4 && ((peer_enable & enables & address)!=0)) $fatal(1,"ownership overlap after edge %0d",edge_count);
if(command==3 && ((pins & enables & address)!=0)) $fatal(1,"open drain drove high %0d",edge_count);
if(actual!==expected) $fatal(1,"clocked edge %0d got %h expected %h",edge_count,actual,expected);
clk=0; edge_count=edge_count+1;
end else $fatal(1,"bad command");
end
"#,
        );
        writeln!(source, "if(edge_count!={}) $fatal(1,\"count\"); $display(\"PROCESSOR PASS: %0d edges\",edge_count); $finish; end endmodule", self.edges).unwrap();
        execute_hdl(self.dir.path(), &source);
        println!("{} clocked HDL edges", self.edges);
    }
}

fn check_uart(
    bytes: &[u8],
    pin: u8,
    period: u32,
    initial: u8,
    ir: &bitlogic::Logic,
    mut hdl: Option<&mut ClockedVectors>,
) {
    let program = uart::transmit(bytes, Pin::new(pin).unwrap(), period).unwrap();
    let words = program.words();
    let symbols = uart_levels(bytes);
    let cycles = symbols.len() * period as usize;
    let mut state = State {
        pins: initial,
        ..State::default()
    };
    if let Some(hdl) = hdl.as_mut() {
        assert_eq!(initial, 0);
        hdl.load(&words);
        hdl.edge(true, 0, State::default());
    }
    for cycle in 0..=cycles {
        let word = words[usize::from(state.pc)];
        let next = state.tick(word, 0, false);
        let mut expected_pins = initial;
        let high = symbols[(cycle / period as usize).min(symbols.len() - 1)];
        if high {
            expected_pins |= 1 << pin;
        } else {
            expected_pins &= !(1 << pin);
        }
        assert_eq!(
            next.pins, expected_pins,
            "{bytes:?} pin={pin} period={period} cycle={cycle}"
        );
        assert_eq!(next.halted, cycle == cycles);
        assert!(!next.fault);
        assert_eq!(native_step(state, word, 0, false), next);
        assert_eq!(ir_step(ir, state, word, 0, false), next);
        if let Some(hdl) = hdl.as_mut() {
            hdl.edge(false, 0, next);
        }
        state = next;
    }
}

#[test]
fn uart_all_bytes_pins_periods_native_ir_and_clocked_hdl() {
    let ir = processor_ir().unwrap();
    let mut hdl = ClockedVectors::new();
    for byte in 0..=u8::MAX {
        for pin in 0..8 {
            for period in [1, 2, 8] {
                check_uart(&[byte], pin, period, 0, &ir, Some(&mut hdl));
                check_uart(&[byte], pin, period, 0xa5, &ir, None);
            }
        }
    }
    for bytes in [&b""[..], &b"Hi"[..], &b"\x00\xff\x55\xaa"[..]] {
        for period in [1, 2, 8] {
            check_uart(bytes, 7, period, 0, &ir, Some(&mut hdl));
        }
    }
    check_uart(&[], 0, 65536, 0, &ir, Some(&mut hdl));
    hdl.finish();
}

#[test]
fn uart_capacity_and_parameters() {
    let pin = Pin::new(0).unwrap();
    for period in [0, 65537, u32::MAX] {
        assert!(uart::transmit(b"", pin, period).is_err());
    }
    for (period, limit) in [(1, 25), (2, 12), (65536, 12)] {
        assert!(uart::transmit(&vec![0; limit], pin, period).is_ok());
        assert!(uart::transmit(&vec![0; limit + 1], pin, period).is_err());
    }
}

#[test]
fn clocked_reset_fault_final_pc_and_unused_rom() {
    let mut hdl = ClockedVectors::new();
    let mut state = State::default();
    // Active wait, halt, malformed instruction and a fall-through into unused ROM.
    for words in [
        vec![0x2000ffff, 0xf0000000],
        vec![0xf0000000],
        vec![0x20000000],
        vec![0x1000ffaa],
    ] {
        hdl.load(&words);
        state = state.tick(0, 0, true);
        hdl.edge(true, 0, state);
        for _ in 0..4 {
            let word = words.get(usize::from(state.pc)).copied().unwrap_or(0);
            state = state.tick(word, 0x96, false);
            hdl.edge(false, 0x96, state);
        }
        state = state.tick(0, 0, true);
        hdl.edge(true, 0, state);
    }
    for final_word in [0xf0000000, 0x1000ffff, 0x20000001] {
        let mut words = vec![0x20000001; 256];
        words[255] = final_word;
        hdl.load(&words);
        state = State::default();
        hdl.edge(true, 0, state);
        for _ in 0..258 {
            state = state.tick(words[usize::from(state.pc)], 0, false);
            hdl.edge(false, 0, state);
        }
    }
    hdl.finish();
}
