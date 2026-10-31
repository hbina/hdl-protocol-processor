use protocol_compiler::{Effect, Pin, drive, protocol, simulate, wait};
use protocol_isa::{Instruction, Machine};

#[protocol]
fn pulse(pin: Pin, high: bool, count: u8) {
    let mut level = high;
    for index in 0..count {
        drive(pin, level);
        match index & 1 {
            0 => wait(2),
            _ => {
                wait(3);
                wait(4);
            }
        }
        level = !level;
    }
    wait(0);
}

#[protocol]
fn composed(pin: Pin, invert: bool, count: u8) {
    let initial = !invert;
    if count > 0 {
        pulse(pin, initial, count);
    }
    pulse(pin, invert, count);
}

#[protocol]
fn mutable_parameter(pin: Pin, mut high: bool) {
    high = !high;
    drive(pin, high);
}

fn wave(effects: &[Effect], initial: u8) -> Vec<u8> {
    let mut pins = initial;
    let mut waveform = Vec::new();
    for effect in effects {
        match *effect {
            Effect::Drive { pin, high } => {
                pins = (pins & !pin.mask()) | if high { pin.mask() } else { 0 };
                waveform.push(pins);
            }
            Effect::Wait(cycles) => waveform.extend(std::iter::repeat_n(pins, cycles as usize)),
        }
    }
    waveform
}

#[test]
fn native_rust_helpers_match_ir_and_instruction_execution() {
    let pin = Pin::new(0).unwrap();
    let native = simulate(|| mutable_parameter(pin, true)).unwrap();
    assert_eq!(
        native.effects,
        mutable_parameter::ir(pin, true).unwrap().effects()
    );
    assert_eq!(
        mutable_parameter::compile(pin, true).unwrap().words(),
        vec![0x1000_0100, 0xf000_0000]
    );
    for pin in 0..8 {
        for invert in [false, true] {
            for count in 0..10 {
                let pin = Pin::new(pin).unwrap();
                let trace = simulate(|| composed(pin, invert, count)).unwrap();
                let ir = composed::ir(pin, invert, count).unwrap();
                assert_eq!(trace.effects, ir.effects());
                let expected = wave(&trace.effects, 0xa5);
                let program = composed::compile(pin, invert, count).unwrap();
                let words = program.words();
                let mut machine = Machine {
                    pins: 0xa5,
                    ..Machine::default()
                };
                for pins in expected {
                    machine.tick(words[machine.pc as usize]);
                    assert!(!machine.halted);
                    assert_eq!(machine.pins, pins);
                }
                machine.tick(words[machine.pc as usize]);
                assert!(machine.halted && !machine.fault);
            }
        }
    }
    assert!(pulse::source().contains("let mut level"));
    assert!(composed::source().contains("pulse"));
}

#[protocol]
fn long_wait(pin: Pin) {
    drive(pin, true);
    drive(pin, true);
    wait(0);
    wait(40_000);
    wait(40_000);
    drive(pin, false);
}

#[test]
fn wait_simplification_preserves_time_and_redundant_drives() {
    let pin = Pin::new(3).unwrap();
    let ir = long_wait::ir(pin).unwrap();
    assert_eq!(ir.effects().len(), 6);
    let program = long_wait::compile(pin).unwrap();
    assert_eq!(program.instructions().len(), 6);
    assert!(matches!(
        program.instructions()[0],
        Instruction::SetPins { .. }
    ));
    assert!(matches!(
        program.instructions()[1],
        Instruction::SetPins { .. }
    ));
    let trace = simulate(|| long_wait(pin)).unwrap();
    let expected = wave(&trace.effects, 0);
    assert_eq!(expected.len(), 80_003);
    let words = program.words();
    let mut machine = Machine::default();
    for pins in expected {
        machine.tick(words[machine.pc as usize]);
        assert_eq!(machine.pins, pins);
        assert!(!machine.halted);
    }
    machine.tick(words[machine.pc as usize]);
    assert!(machine.halted && !machine.fault);
}

#[protocol]
fn too_much_work(count: usize) {
    for _ in 0..count {}
}

#[test]
fn bounded_specialization_and_native_capture_cleanup() {
    assert!(simulate(|| too_much_work(0)).unwrap().effects.is_empty());
    assert_eq!(
        too_much_work::compile(0).unwrap().instructions(),
        &[Instruction::Halt]
    );
    assert!(
        too_much_work::compile(65_537)
            .unwrap_err()
            .to_string()
            .contains("loop iterations")
    );
    let pin = Pin::new(0).unwrap();
    let panic = std::panic::catch_unwind(|| {
        let _ = simulate(|| panic!("test unwind"));
    });
    assert!(panic.is_err());
    simulate(|| {
        assert!(simulate(|| {}).is_err());
        drive(pin, true);
    })
    .unwrap();
    assert_eq!(simulate(|| wait(2)).unwrap().effects, vec![Effect::Wait(2)]);
}
