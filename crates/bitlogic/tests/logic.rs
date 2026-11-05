use bitlogic::{Binary, Bits, Builder, bits, logic};
use protocol_isa::{Instruction, Machine};
use std::{fmt::Write, process::Command};

#[logic]
fn transform(a: &Bits<3>, b: &Bits<3>, enabled: &bool, result: &mut Bits<3>, different: &mut bool) {
    let mut value = *a ^ *b;
    if *enabled {
        value = value + bits::<3>(3);
    } else {
        value = !value;
    }
    *result = value;
    *different = *a != *b;
}

#[logic]
fn conditional(a: &Bits<3>, b: &Bits<3>, result: &mut Bits<3>, flag: &mut bool) {
    *result = if *a < *b { *a } else { *b };
    *flag = false;
    if *a == *b {
        *flag = true;
    } else if *a > bits::<3>(3) {
        *flag = a.bit(0);
    }
}

#[logic]
fn slices(a: &Bits<4>, result: &mut Bits<4>) {
    let low = a.slice::<2>(0);
    let high = a.slice::<2>(2);
    *result = low.concat::<2, 4>(high);
    for _ in 0..2 {
        *result = (*result << 1) ^ bits::<4>(3);
    }
}

#[logic]
fn invert(a: &Bits<3>, result: &mut Bits<3>) {
    *result = !*a;
}

fn execute(program: &protocol_isa::Program, inputs: u8, initial: u8) -> Machine {
    let mut machine = Machine {
        pins: initial,
        ..Machine::default()
    };
    for word in program.words() {
        machine.tick_with_inputs(word, inputs);
    }
    assert!(machine.halted && !machine.fault);
    machine
}

#[test]
fn native_ir_and_runtime_processor_match_independent_truth_tables() {
    let ir = transform::ir().unwrap();
    let program = ir.to_program().unwrap();
    let conditional = conditional::ir().unwrap();
    let conditional_program = conditional.to_program().unwrap();
    for a in 0..8_u64 {
        for b in 0..8_u64 {
            for enabled in [false, true] {
                let mut result = bits::<3>(0);
                let mut different = false;
                transform(&bits(a), &bits(b), &enabled, &mut result, &mut different);
                let expected = if enabled {
                    ((a ^ b) + 3) & 7
                } else {
                    (!(a ^ b)) & 7
                };
                let flag = u64::from(a != b);
                assert_eq!((result.get(), u64::from(different)), (expected, flag));
                assert_eq!(
                    ir.evaluate(&[a, b, u64::from(enabled)]).unwrap(),
                    [expected, flag]
                );
                let input = (a | (b << 3) | (u64::from(enabled) << 6)) as u8;
                let observed = execute(&program, input, 0xf0).pins;
                assert_eq!(observed, 0xf0 | expected as u8 | ((flag as u8) << 3));

                let mut result = bits::<3>(0);
                let mut flag = false;
                super_conditional(a, b, &mut result, &mut flag);
                let expected_flag = a == b || (a > 3 && a & 1 != 0);
                assert_eq!(
                    conditional.evaluate(&[a, b]).unwrap(),
                    [a.min(b), u64::from(expected_flag)]
                );
                assert_eq!((result.get(), flag), (a.min(b), expected_flag));
                assert_eq!(
                    execute(&conditional_program, (a | (b << 3)) as u8, 0).pins,
                    u8::try_from(a.min(b)).unwrap() | (u8::from(expected_flag) << 3)
                );
            }
        }
    }
    for a in 0..16 {
        let mut result = bits::<4>(0);
        slices(&bits(a), &mut result);
        let rotated = ((a & 3) << 2) | (a >> 2);
        let expected = ((((rotated << 1) ^ 3) << 1) ^ 3) & 15;
        let ir = slices::ir().unwrap();
        assert_eq!(result.get(), expected);
        assert_eq!(ir.evaluate(&[a]).unwrap(), [expected]);
        assert_eq!(
            execute(&ir.to_program().unwrap(), a as u8, 0).pins,
            expected as u8
        );
    }
}
fn super_conditional(a: u64, b: u64, result: &mut Bits<3>, flag: &mut bool) {
    conditional(&bits(a), &bits(b), result, flag);
}

#[test]
fn composition_and_pin_mapping_preserve_values() {
    let twice = invert::ir().unwrap().then(&invert::ir().unwrap()).unwrap();
    let program = twice.to_program_with_pins(&[7, 5, 3], &[6, 4, 2]).unwrap();
    for value in 0..8 {
        let mut native = bits::<3>(0);
        invert(&bits(value), &mut native);
        assert_eq!(native.get(), (!value) & 7);
        assert_eq!(twice.evaluate(&[value]).unwrap(), [value]);
        let input = (((value & 1) << 7) | ((value & 2) << 4) | ((value & 4) << 1)) as u8;
        let expected = (((value & 1) << 6) | ((value & 2) << 3) | (value & 4)) as u8;
        assert_eq!(execute(&program, input, 0x83).pins, expected | 0x83);
    }
    assert!(twice.to_program_with_pins(&[0, 1, 2], &[0, 0, 1]).is_err());
    assert!(twice.to_program_with_pins(&[0, 1, 8], &[0, 1, 2]).is_err());
    assert!(twice.to_program_with_pins(&[], &[]).is_err());
    assert!(twice.evaluate(&[8]).is_err());
    assert!(twice.evaluate(&[]).is_err());
    assert!(twice.to_verilog("bad-name").is_err());
    assert!(twice.then(&transform::ir().unwrap()).is_err());
}

fn binary_ir(op: Binary, width: u8) -> bitlogic::Logic {
    let mut b = Builder::default();
    let a = b.input("a", width).unwrap();
    let rhs = b.input("b", width).unwrap();
    let result = b.binary(op, a, rhs).unwrap();
    b.output("result", result).unwrap();
    b.finish().unwrap()
}

#[test]
fn every_binary_operation_and_width_boundary_has_defined_semantics() {
    for op in [
        Binary::And,
        Binary::Or,
        Binary::Xor,
        Binary::Add,
        Binary::Sub,
        Binary::Eq,
        Binary::Ne,
        Binary::Lt,
        Binary::Le,
        Binary::Gt,
        Binary::Ge,
    ] {
        let small = binary_ir(op, 3);
        let program = small.to_program().unwrap();
        for a in 0..8_u64 {
            for b in 0..8_u64 {
                let expected = match op {
                    Binary::And => a & b,
                    Binary::Or => a | b,
                    Binary::Xor => a ^ b,
                    Binary::Add => (a + b) & 7,
                    Binary::Sub => a.wrapping_sub(b) & 7,
                    Binary::Eq => u64::from(a == b),
                    Binary::Ne => u64::from(a != b),
                    Binary::Lt => u64::from(a < b),
                    Binary::Le => u64::from(a <= b),
                    Binary::Gt => u64::from(a > b),
                    Binary::Ge => u64::from(a >= b),
                };
                assert_eq!(small.evaluate(&[a, b]).unwrap(), [expected]);
                assert_eq!(
                    execute(&program, (a | (b << 3)) as u8, 0).pins,
                    expected as u8,
                    "{op:?} {a} {b}"
                );
            }
        }
        let wide = binary_ir(op, 64);
        assert!(wide.to_program().is_err());
        assert!(wide.evaluate(&[u64::MAX, 1]).is_ok());
    }
    assert_eq!((bits::<64>(u64::MAX) + bits(1)).get(), 0);
    assert_eq!((bits::<1>(0) - bits(1)).get(), 1);
    assert_eq!((bits::<64>(1) << 64).get(), 0);
    assert_eq!((bits::<64>(u64::MAX) >> 64).get(), 0);
    let mut b = Builder::default();
    assert!(b.input("bad", 0).is_err());
    let a = b.input("a", 64).unwrap();
    assert!(b.concat(a, a).is_err());
}

fn run_hdl(source: String, marker: &str) {
    let dir = tempfile::tempdir().unwrap();
    let hdl = dir.path().join("test.v");
    let executable = dir.path().join("test.vvp");
    std::fs::write(&hdl, source).unwrap();
    let output = Command::new("iverilog")
        .args(["-g2012", "-s", "tb", "-o"])
        .arg(&executable)
        .arg(&hdl)
        .output()
        .expect("Icarus Verilog is required");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let output = Command::new("vvp").arg(executable).output().unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        output.status.success() && stdout.contains(marker),
        "{stdout}\n{}",
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn emitted_combinational_hdl_matches_independent_oracle() {
    let mut source = transform::ir().unwrap().to_verilog("transform").unwrap();
    source.push_str("module tb; reg [2:0] a,b;reg enabled;wire [2:0] result;wire different;integer i,j,k;reg [2:0] expected;\ntransform dut(.i_a(a),.i_b(b),.i_enabled(enabled),.o_result(result),.o_different(different));\ninitial begin\nfor(i=0;i<8;i=i+1)for(j=0;j<8;j=j+1)for(k=0;k<2;k=k+1) begin\na=i;b=j;enabled=k;expected=k ? ((i^j)+3) : ~(i^j);#1;\nif(result !== expected || different !== (i!=j)) $fatal(1,\"logic mismatch\");end\n$display(\"LOGIC PASS\");$finish;end endmodule\n");
    run_hdl(source, "LOGIC PASS");
}

#[test]
fn emitted_hdl_covers_all_operators_and_64_bit_boundaries() {
    let ops = [
        Binary::And,
        Binary::Or,
        Binary::Xor,
        Binary::Add,
        Binary::Sub,
        Binary::Eq,
        Binary::Ne,
        Binary::Lt,
        Binary::Le,
        Binary::Gt,
        Binary::Ge,
    ];
    let mut source = String::new();
    let mut declarations = String::new();
    let mut checks = String::new();
    let values = [
        0,
        1,
        2,
        3,
        7,
        u64::MAX,
        u64::MAX - 1,
        1 << 63,
        0x1234_5678_9abc_def0,
    ];
    for width in [1, 3, 64] {
        for (index, op) in ops.into_iter().enumerate() {
            let ir = binary_ir(op, width);
            let name = format!("op_{width}_{index}");
            source.push_str(&ir.to_verilog(&name).unwrap());
            let out_width = ir.outputs()[0].width;
            writeln!(declarations,"wire [{}:0] r_{name}; {name} d_{name}(.i_a(a[{}:0]),.i_b(b[{}:0]),.o_result(r_{name}));",out_width-1,width-1,width-1).unwrap();
            let mask = u64::MAX >> (64 - width);
            for a in values {
                for b in values {
                    let (av, bv) = (a & mask, b & mask);
                    let expected = match op {
                        Binary::And => av & bv,
                        Binary::Or => av | bv,
                        Binary::Xor => av ^ bv,
                        Binary::Add => av.wrapping_add(bv) & mask,
                        Binary::Sub => av.wrapping_sub(bv) & mask,
                        Binary::Eq => u64::from(av == bv),
                        Binary::Ne => u64::from(av != bv),
                        Binary::Lt => u64::from(av < bv),
                        Binary::Le => u64::from(av <= bv),
                        Binary::Gt => u64::from(av > bv),
                        Binary::Ge => u64::from(av >= bv),
                    };
                    writeln!(checks,"a=64'h{a:x};b=64'h{b:x};#1;if(r_{name} !== {out_width}'h{expected:x})$fatal(1,\"{name}\");").unwrap();
                }
            }
        }
    }
    // Exercise the frontend's slice/concat/shift lowering in real HDL as well.
    source.push_str(&slices::ir().unwrap().to_verilog("slices").unwrap());
    declarations.push_str("wire [3:0] swapped; slices ds(.i_a(a[3:0]),.o_result(swapped));\n");
    for value in 0..16_u64 {
        let rotated = ((value & 3) << 2) | (value >> 2);
        let expected = ((((rotated << 1) ^ 3) << 1) ^ 3) & 15;
        writeln!(
            checks,
            "a=64'd{value};#1;if(swapped!==4'd{expected})$fatal(1,\"slice/concat/shift\");"
        )
        .unwrap();
    }
    for (index, (amount, left)) in [(0, true), (3, true), (64, true), (u32::MAX, false)]
        .into_iter()
        .enumerate()
    {
        let mut builder = Builder::default();
        let a = builder.input("a", 64).unwrap();
        let result = builder.shift(a, amount, left).unwrap();
        builder.output("result", result).unwrap();
        let name = format!("shift_{index}");
        source.push_str(&builder.finish().unwrap().to_verilog(&name).unwrap());
        writeln!(
            declarations,
            "wire [63:0] r_{name};{name} d_{name}(.i_a(a),.o_result(r_{name}));"
        )
        .unwrap();
        for value in values {
            let expected = if left {
                value.checked_shl(amount)
            } else {
                value.checked_shr(amount)
            }
            .unwrap_or(0);
            writeln!(
                checks,
                "a=64'h{value:x};#1;if(r_{name}!==64'h{expected:x})$fatal(1,\"{name}\");"
            )
            .unwrap();
        }
    }
    write!(source,"module tb;reg [63:0] a,b;\n{declarations}\ninitial begin\n{checks}\n$display(\"OPERATORS PASS\");$finish;end endmodule\n").unwrap();
    run_hdl(source, "OPERATORS PASS");
}

#[test]
fn emitted_clocked_processor_executes_captured_logic_with_one_input_snapshot() {
    let program = transform::ir().unwrap().to_program().unwrap();
    let words = program.words();
    let mut source = protocol_processor::emit_verilog().unwrap();
    source.push_str("module tb;reg clk=0,reset=1;reg [7:0] inputs=0;wire [7:0] pc,pins;wire [15:0] wait_remaining;wire halted,fault;reg [31:0] rom[0:255];integer i;wire [31:0] instruction=rom[pc];\nprotocol_processor dut(.clk(clk),.reset(reset),.inputs(inputs),.instruction(instruction),.pc(pc),.pins(pins),.wait_remaining(wait_remaining),.halted(halted),.fault(fault));\ninitial begin for(i=0;i<256;i=i+1)rom[i]=32'hf0000000;\n");
    for (i, word) in words.iter().enumerate() {
        writeln!(source, "rom[{i}]=32'h{word:08x};").unwrap();
    }
    let mut observations = 0;
    for a in 0..8_u8 {
        for b in 0..8_u8 {
            for enabled in [false, true] {
                let input = a | (b << 3) | (u8::from(enabled) << 6);
                writeln!(
                    source,
                    "clk=0;reset=1;inputs=8'd{input};#4;clk=1;#1;clk=0;reset=0;"
                )
                .unwrap();
                let mut machine = Machine::default();
                let mut state = protocol_processor::State::default();
                for (index, word) in words.iter().enumerate() {
                    // Changes after CAPTURE_INPUTS must not change this invocation's result.
                    let current = if index == 0 { input } else { !input };
                    machine.tick_with_inputs(*word, current);
                    state = protocol_processor::step_with_inputs(
                        rhdl::prelude::bits(u128::from(*word)),
                        rhdl::prelude::bits(u128::from(current)),
                        state,
                    );
                    assert_eq!(state.pc.raw(), u128::from(machine.pc));
                    assert_eq!(state.scratch.raw(), u128::from(machine.scratch));
                    assert_eq!(state.pins.raw(), u128::from(machine.pins));
                    assert_eq!(state.halted, machine.halted);
                    assert_eq!(state.fault, machine.fault);
                    writeln!(source,"inputs=8'd{current};#4;clk=1;#1;if(pc!==8'd{} || pins!==8'd{} || halted!==1'b{} || fault!==1'b{})$fatal(1,\"processor cycle {observations}\");clk=0;",machine.pc,machine.pins,u8::from(machine.halted),u8::from(machine.fault)).unwrap();
                    observations += 1;
                }
                let expected = if enabled {
                    (a ^ b).wrapping_add(3) & 7
                } else {
                    !(a ^ b) & 7
                };
                assert_eq!(machine.pins, expected | (u8::from(a != b) << 3));
            }
        }
    }
    source.push_str("$display(\"LOGIC PROCESSOR PASS\");$finish;end initial begin #1000000;$fatal(1,\"timeout\");end endmodule\n");
    run_hdl(source, "LOGIC PROCESSOR PASS");
    println!("Untimed logic on clocked processor: {observations} cycle observations");
    assert_eq!(words.last(), Some(&Instruction::Halt.encode()));
}
