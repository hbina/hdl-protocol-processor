use bitlogic::{Binary, Bits, Builder, LogicValue, bits, logic};
use std::{fmt::Write, process::Command};

#[derive(Clone, Copy, LogicValue)]
struct TransformInput {
    a: Bits<3>,
    b: Bits<3>,
    enabled: bool,
}
#[derive(Clone, Copy, LogicValue)]
struct TransformOutput {
    result: Bits<3>,
    different: bool,
}
#[derive(Clone, Copy, LogicValue)]
struct Pair {
    a: Bits<3>,
    b: Bits<3>,
}
#[derive(Clone, Copy, LogicValue)]
struct ConditionalOutput {
    result: Bits<3>,
    flag: bool,
}

#[logic]
fn transform(input: TransformInput) -> TransformOutput {
    let value = input.a ^ input.b;
    TransformOutput {
        result: if input.enabled {
            value + bits::<3>(3)
        } else {
            !value
        },
        different: input.a != input.b,
    }
}

#[logic]
fn conditional(input: Pair) -> ConditionalOutput {
    ConditionalOutput {
        result: if input.a < input.b { input.a } else { input.b },
        flag: if input.a == input.b {
            true
        } else if input.a > bits::<3>(3) {
            input.a.bit(0)
        } else {
            false
        },
    }
}

#[logic]
fn slices(a: Bits<4>) -> Bits<4> {
    let low = a.slice::<2>(0);
    let high = a.slice::<2>(2);
    low.concat::<2, 4>(high)
        .fold::<2>(|value, _index| (value << 1) ^ bits::<4>(3))
}

#[logic]
fn invert(a: Bits<3>) -> Bits<3> {
    !a
}

#[test]
fn native_and_ir_match_independent_truth_tables() {
    let ir = transform::ir().unwrap();
    let conditional_ir = conditional::ir().unwrap();
    for a in 0..8_u64 {
        for b in 0..8_u64 {
            for enabled in [false, true] {
                let TransformOutput { result, different } = transform(TransformInput {
                    a: bits(a),
                    b: bits(b),
                    enabled,
                });
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
            }
            let ConditionalOutput { result, flag } = conditional(Pair {
                a: bits(a),
                b: bits(b),
            });
            let expected_flag = a == b || (a > 3 && a & 1 != 0);
            assert_eq!(
                conditional_ir.evaluate(&[a, b]).unwrap(),
                [a.min(b), u64::from(expected_flag)]
            );
            assert_eq!((result.get(), flag), (a.min(b), expected_flag));
        }
    }
    let ir = slices::ir().unwrap();
    for a in 0..16 {
        let result = slices(bits(a));
        let rotated = ((a & 3) << 2) | (a >> 2);
        let expected = ((((rotated << 1) ^ 3) << 1) ^ 3) & 15;
        assert_eq!(result.get(), expected);
        assert_eq!(ir.evaluate(&[a]).unwrap(), [expected]);
    }
}

#[test]
fn composition_preserves_values_and_checks_port_shapes() {
    let twice = invert::ir().unwrap().then(&invert::ir().unwrap()).unwrap();
    for value in 0..8 {
        let native = invert(bits(value));
        assert_eq!(native.get(), (!value) & 7);
        assert_eq!(twice.evaluate(&[value]).unwrap(), [value]);
    }
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
            }
        }
        assert!(binary_ir(op, 64).evaluate(&[u64::MAX, 1]).is_ok());
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
