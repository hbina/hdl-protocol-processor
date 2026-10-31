use std::{fmt::Write, num::NonZeroU16, process::Command};

use protocol_isa::{Instruction, Machine, PROGRAM_CAPACITY, Pin};
use protocol_processor::{State, step};
use rhdl::prelude::*;

fn hardware_state(machine: Machine) -> State {
    State {
        pc: bits(machine.pc.into()),
        wait_remaining: bits(machine.wait_remaining.into()),
        pins: bits(machine.pins.into()),
        halted: machine.halted,
        fault: machine.fault,
    }
}

#[test]
fn every_uart_byte_pin_and_bit_period_matches_independent_waveform() {
    for pin_index in 0..8 {
        let mask = 1_u8 << pin_index;
        for period in [1, 2, 8] {
            for byte in 0..=255_u8 {
                let program = protocol_compiler::uart_tx::compile(
                    &[byte],
                    Pin::new(pin_index).unwrap(),
                    NonZeroU16::new(period).unwrap(),
                )
                .unwrap();
                let words = program.words();
                let native = protocol_compiler::simulate(|| {
                    protocol_compiler::uart_tx(
                        &[byte],
                        Pin::new(pin_index).unwrap(),
                        NonZeroU16::new(period).unwrap(),
                    );
                })
                .unwrap();
                let ir = protocol_compiler::uart_tx::ir(
                    &[byte],
                    Pin::new(pin_index).unwrap(),
                    NonZeroU16::new(period).unwrap(),
                )
                .unwrap();
                assert_eq!(native.effects, ir.effects());
                let mut reference = Machine {
                    pins: 0xa5,
                    ..Machine::default()
                };
                let mut state = hardware_state(reference);
                for cycle in 0..11 * usize::from(period) {
                    let word = words[reference.pc as usize];
                    reference.tick(word);
                    state = step(bits(word.into()), state);
                    assert_eq!(state, hardware_state(reference));
                    let bit_index = cycle / usize::from(period);
                    let high = match bit_index {
                        0 | 10 => true,
                        1 => false,
                        2..=9 => byte & (1 << (bit_index - 2)) != 0,
                        _ => unreachable!(),
                    };
                    assert_eq!(reference.pins, (0xa5 & !mask) | if high { mask } else { 0 });
                    assert!(!reference.halted);
                }
                let halt = words[reference.pc as usize];
                state = step(bits(halt.into()), state);
                assert!(state.halted && !state.fault);
                assert_eq!(step(bits(0), state), state);
            }
        }
    }
}

#[test]
fn compiled_kernel_matches_reference_on_boundary_and_malformed_words() {
    let mut cases = Vec::new();
    let words = [
        0,
        0x1000_ff55,
        0x1000_00ff,
        0x1001_0000,
        0x2000_0000,
        0x2000_0001,
        0x2000_0002,
        0x2000_ffff,
        0x2001_0001,
        0xf000_0000,
        0xf000_0001,
        0xffff_ffff,
    ];
    for pc in [0, 254, 255] {
        for wait_remaining in [0, 1, 2, u16::MAX] {
            for pins in [0, 0x55, 0xff] {
                for halted in [false, true] {
                    for word in words {
                        let mut reference = Machine {
                            pc,
                            wait_remaining,
                            pins,
                            halted,
                            fault: false,
                        };
                        let before = hardware_state(reference);
                        reference.tick(word);
                        assert_eq!(step(bits(word.into()), before), hardware_state(reference));
                        cases.push((bits(word.into()), before));
                    }
                }
            }
        }
    }
    // Pinned internal upstream API checks RHIF/RTL VMs and two Verilog lowerings.
    rhdl::core::sim::testbench::kernel::test_kernel_vm_and_verilog_synchronous::<step, _, _, _>(
        step,
        cases.into_iter(),
    )
    .unwrap();
}

#[test]
fn emitted_clocked_processor_matches_reference_cycle_by_cycle() {
    let directory = tempfile::tempdir().unwrap();
    let mut source = protocol_processor::emit_verilog().unwrap();
    source.push_str("\nmodule tb;\nreg clk = 0; reg reset = 1;\nreg [31:0] rom [0:255];\nwire [7:0] pc, pins; wire [15:0] wait_remaining;\nwire halted, fault; wire [31:0] instruction = rom[pc]; integer i;\nprotocol_processor dut(.clk(clk), .reset(reset), .instruction(instruction), .pc(pc), .pins(pins), .wait_remaining(wait_remaining), .halted(halted), .fault(fault));\ninitial begin\n");

    let mut scenarios = Vec::new();
    for pin in [0, 7] {
        for period in [1, 2, 8] {
            let program = protocol_compiler::uart_tx::compile(
                &[0, 0xff, 0x55, 0xa5],
                Pin::new(pin).unwrap(),
                NonZeroU16::new(period).unwrap(),
            )
            .unwrap();
            scenarios.push((program.words(), 41 * period as usize + 3));
        }
    }
    // Stop mid-WAIT so the following scenario checks reset clears an active wait.
    scenarios.push((vec![0x2000_ffff], 2));
    for invalid in [0, 0x2000_0000, 0x1001_0000, 0xf000_0001] {
        scenarios.push((vec![0x1000_ffff, invalid], 4));
    }
    // A full image must halt at 255, or fault there instead of wrapping its PC.
    let mut full = vec![0x2000_0001; PROGRAM_CAPACITY];
    full[255] = Instruction::Halt.encode();
    scenarios.push((full, 258));
    scenarios.push((vec![0x1000_0101; PROGRAM_CAPACITY], 258));

    let mut observations = 0;
    for (words, cycles) in scenarios {
        // Each reset also exercises recovery from an earlier halt/fault/wait.
        source.push_str("clk = 0; reset = 1; for (i=0; i<256; i=i+1) rom[i] = 32'hf0000000;\n");
        for (index, word) in words.iter().enumerate() {
            writeln!(source, "rom[{index}] = 32'h{word:08x};").unwrap();
        }
        source.push_str("#4; clk = 1; #1; if ({pc, wait_remaining, pins, halted, fault} !== 34'b0) $fatal(1, \"reset failed\"); clk = 0; reset = 0;\n");
        let mut reference = Machine::default();
        for _ in 0..cycles {
            let word = words
                .get(reference.pc as usize)
                .copied()
                .unwrap_or(Instruction::Halt.encode());
            reference.tick(word);
            writeln!(source,
                "#4; clk = 1; #1; if (pc !== 8'd{} || wait_remaining !== 16'd{} || pins !== 8'd{} || halted !== 1'b{} || fault !== 1'b{}) $fatal(1, \"cycle {observations}\"); clk = 0;",
                reference.pc, reference.wait_remaining, reference.pins,
                u8::from(reference.halted), u8::from(reference.fault),
            ).unwrap();
            observations += 1;
        }
    }
    source.push_str("$display(\"PROCESSOR PASS\"); $finish; end\ninitial begin #1000000; $fatal(1, \"timeout\"); end\nendmodule\n");
    let hdl = directory.path().join("test.v");
    let executable = directory.path().join("test.vvp");
    std::fs::write(&hdl, source).unwrap();
    let compile = Command::new("iverilog")
        .args(["-g2012", "-s", "tb", "-o"])
        .arg(&executable)
        .arg(&hdl)
        .output()
        .unwrap();
    assert!(
        compile.status.success(),
        "{}",
        String::from_utf8_lossy(&compile.stderr)
    );
    let simulation = Command::new("vvp").arg(executable).output().unwrap();
    let stdout = String::from_utf8_lossy(&simulation.stdout);
    assert!(
        simulation.status.success(),
        "{stdout}\n{}",
        String::from_utf8_lossy(&simulation.stderr)
    );
    assert!(stdout.contains("PROCESSOR PASS"), "{stdout}");
    println!("Clocked processor: {observations} cycle observations passed");
}
