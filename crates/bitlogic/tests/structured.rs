use bitlogic::{Bits, LogicValue, Schema, bits, logic};
use std::{fmt::Write, process::Command};

mod types {
    use super::*;
    #[derive(Clone, Copy, Debug, PartialEq, Eq, LogicValue)]
    pub struct State {
        pub counter: Bits<3>,
        pub enabled: bool,
    }
}
use types::State;

#[derive(Clone, Copy, LogicValue)]
struct Input {
    state: State,
    reset: bool,
    unused: Bits<2>,
    wire: Bits<1>,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, LogicValue)]
struct Output {
    state: State,
    checksum: bool,
}

#[logic]
fn step(input: Input) -> Output {
    let counter = input.state.counter;
    let counter: Bits<3> = if input.state.enabled {
        counter + bits::<3>(1)
    } else {
        counter
    };
    let next = if input.reset {
        types::State {
            counter: bits::<3>(0),
            enabled: false,
        }
    } else {
        types::State {
            enabled: input.state.enabled,
            counter,
        }
    };
    Output {
        checksum: next.counter.bit(0),
        state: next,
    }
}

#[logic]
fn identity(input: State) -> State {
    input
}
#[logic]
fn increment(input: State) -> State {
    State {
        counter: input.counter + bits::<3>(1),
        enabled: input.enabled,
    }
}
#[logic]
fn complement(input: State) -> State {
    State {
        counter: !input.counter,
        enabled: !input.enabled,
    }
}
#[derive(Clone, Copy, LogicValue)]
struct Other {
    counter: Bits<3>,
    enabled: bool,
}
#[logic]
fn other(input: Other) -> Other {
    input
}
#[logic]
fn adapter(input: State) -> Other {
    Other {
        counter: input.counter,
        enabled: input.enabled,
    }
}
#[logic]
fn boolean(input: bool) -> bool {
    input
}
#[logic]
fn one_bit(input: Bits<1>) -> Bits<1> {
    input
}

#[test]
fn nested_schema_round_trip_and_validation() {
    let value = Input {
        state: State {
            counter: bits(7),
            enabled: true,
        },
        reset: false,
        unused: bits(2),
        wire: bits(1),
    };
    assert_eq!(value.flatten(), [7, 1, 0, 2, 1]);
    assert_eq!(
        Input::from_values(&value.flatten()).unwrap().flatten(),
        value.flatten()
    );
    let leaves = Input::schema().leaves();
    assert_eq!(
        leaves,
        vec![
            ("state.counter".into(), Schema::Bits(3)),
            ("state.enabled".into(), Schema::Bool),
            ("reset".into(), Schema::Bool),
            ("unused".into(), Schema::Bits(2)),
            ("wire".into(), Schema::Bits(1)),
        ]
    );
    for invalid in [
        vec![],
        vec![8, 0, 0, 0, 0],
        vec![0, 2, 0, 0, 0],
        vec![0, 0, 0, 4, 0],
        vec![0, 0, 0, 0, 2],
        vec![0, 0, 0, 0, 0, 0],
    ] {
        assert!(Input::from_values(&invalid).is_err(), "{invalid:?}");
    }
    assert!(Bits::<65>::from_values(&[0]).is_err());
    #[derive(Clone, Copy, LogicValue)]
    struct Raw {
        r#type: bool,
    }
    #[logic]
    fn raw(input: Raw) -> Raw {
        input
    }
    assert!(raw(Raw { r#type: true }).r#type);
    let raw_ir = raw::ir().unwrap();
    assert_eq!(raw_ir.inputs()[0].name, "type");
    let renamed = raw_ir
        .clone()
        .rename_ports(&["pin"], &["next_pin"])
        .unwrap();
    assert_eq!(renamed.schemas(), raw_ir.schemas());
    assert_eq!(renamed.dependencies(), raw_ir.dependencies());
    assert!(raw_ir.clone().rename_ports(&[], &["pin"]).is_err());
    assert!(raw_ir.rename_ports(&["bad-name"], &["pin"]).is_err());
    let ir = step::ir().unwrap();
    assert_eq!(
        ir.inputs()
            .iter()
            .map(|p| p.name.as_str())
            .collect::<Vec<_>>(),
        ["state_counter", "state_enabled", "reset", "unused", "wire"]
    );
    assert_eq!(
        ir.outputs()
            .iter()
            .map(|p| p.name.as_str())
            .collect::<Vec<_>>(),
        ["state_counter", "state_enabled", "checksum"]
    );
    assert!(ir.evaluate_typed::<_, State>(value).is_err());
}

#[test]
fn aggregates_native_ir_and_hdl_match_independent_expectations() {
    let ir = step::ir().unwrap();
    let mut source = ir.to_verilog("step").unwrap();
    source.push_str("module tb;reg [2:0] counter;reg enabled,reset;reg [1:0] unused;reg wire_value;wire [2:0] next_counter;wire next_enabled,checksum;\nstep dut(.i_state_counter(counter),.i_state_enabled(enabled),.i_reset(reset),.i_unused(unused),.i_wire(wire_value),.o_state_counter(next_counter),.o_state_enabled(next_enabled),.o_checksum(checksum));initial begin\n");
    for counter in 0..8 {
        for enabled in [false, true] {
            for reset in [false, true] {
                for unused in 0..4 {
                    for wire in 0..2 {
                        let input = Input {
                            state: State {
                                counter: bits(counter),
                                enabled,
                            },
                            reset,
                            unused: bits(unused),
                            wire: bits(wire),
                        };
                        let next = if reset {
                            0
                        } else {
                            (counter + u64::from(enabled)) % 8
                        };
                        let expected = Output {
                            state: State {
                                counter: bits(next),
                                enabled: enabled && !reset,
                            },
                            checksum: next % 2 == 1,
                        };
                        assert_eq!(step(input), expected);
                        assert_eq!(ir.evaluate_typed::<_, Output>(input).unwrap(), expected);
                        writeln!(source,"counter=3'd{counter};enabled=1'd{};reset=1'd{};unused=2'd{unused};wire_value=1'd{wire};#1;if(next_counter!==3'd{next} || next_enabled!==1'd{} || checksum!==1'd{}) $fatal(1,\"aggregate\");",u8::from(enabled),u8::from(reset),u8::from(enabled&&!reset),next%2).unwrap();
                    }
                }
            }
        }
    }
    source.push_str("$display(\"STRUCTURED PASS\");$finish;end endmodule\n");
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("test.v");
    let executable = dir.path().join("test.vvp");
    std::fs::write(&path, source).unwrap();
    let compile = Command::new("iverilog")
        .args(["-g2012", "-s", "tb", "-o"])
        .arg(&executable)
        .arg(path)
        .output()
        .unwrap();
    assert!(
        compile.status.success(),
        "{}",
        String::from_utf8_lossy(&compile.stderr)
    );
    let run = Command::new("vvp").arg(executable).output().unwrap();
    assert!(
        run.status.success() && String::from_utf8_lossy(&run.stdout).contains("STRUCTURED PASS"),
        "{}",
        String::from_utf8_lossy(&run.stdout)
    );
}

#[test]
fn dependencies_include_predicates_and_exclude_unused_inputs() {
    let ir = step::ir().unwrap();
    assert_eq!(
        ir.dependencies(),
        vec![
            (
                "state.counter".into(),
                vec![
                    "state.counter".into(),
                    "state.enabled".into(),
                    "reset".into()
                ]
            ),
            (
                "state.enabled".into(),
                vec!["state.enabled".into(), "reset".into()]
            ),
            (
                "checksum".into(),
                vec![
                    "state.counter".into(),
                    "state.enabled".into(),
                    "reset".into()
                ]
            ),
        ]
    );
    #[logic]
    fn canceled(value: Bits<3>) -> Bits<3> {
        value ^ value
    }
    assert_eq!(canceled(bits(5)), bits(0));
    assert_eq!(
        canceled::ir().unwrap().dependencies(),
        vec![("result".into(), vec!["value".into()])]
    );
    assert!(!ir.nodes().is_empty());
}

#[test]
fn composition_checks_nominal_types_and_satisfies_laws() {
    let f = increment::ir().unwrap();
    let g = complement::ir().unwrap();
    let id = identity::ir().unwrap();
    assert!(id.then(&other::ir().unwrap()).is_err());
    assert!(
        boolean::ir()
            .unwrap()
            .then(&one_bit::ir().unwrap())
            .is_err()
    );
    assert!(boolean(true));
    assert_eq!(one_bit(bits(1)), bits(1));
    let adapted = id
        .then(&adapter::ir().unwrap())
        .unwrap()
        .then(&other::ir().unwrap())
        .unwrap();
    let left = f.then(&g).unwrap().then(&f).unwrap();
    let right = f.then(&g.then(&f).unwrap()).unwrap();
    for counter in 0..8 {
        for enabled in [false, true] {
            let input = State {
                counter: bits(counter),
                enabled,
            };
            let expected = increment(complement(increment(input)));
            assert_eq!(left.evaluate_typed::<_, State>(input).unwrap(), expected);
            assert_eq!(right.evaluate_typed::<_, State>(input).unwrap(), expected);
            for composed in [id.then(&f).unwrap(), f.then(&id).unwrap()] {
                assert_eq!(
                    composed.evaluate_typed::<_, State>(input).unwrap(),
                    increment(input)
                );
            }
            assert_eq!(
                adapted.evaluate_typed::<_, Other>(input).unwrap().flatten(),
                other(adapter(identity(input))).flatten()
            );
        }
    }
    let mut builder = bitlogic::Builder::default();
    let a = builder.input("a", 3).unwrap();
    builder.output("a", a).unwrap();
    assert!(builder.finish().unwrap().then(&f).is_err());
}

#[test]
fn collisions_and_bad_bit_operations_fail_during_capture() {
    #[derive(Clone, Copy, LogicValue)]
    struct Nested {
        b: bool,
    }
    #[derive(Clone, Copy, LogicValue)]
    struct Collision {
        a_b: bool,
        a: Nested,
    }
    #[logic]
    fn collide(input: Collision) -> Collision {
        input
    }
    assert!(collide::ir().unwrap_err().0.contains("duplicate input"));
    let _ = collide(Collision {
        a_b: true,
        a: Nested { b: false },
    });
    #[derive(Clone, Copy, LogicValue)]
    struct Safe {
        x: bool,
        y: bool,
    }
    #[logic]
    fn output_collision(input: Safe) -> Collision {
        Collision {
            a_b: input.x,
            a: Nested { b: input.y },
        }
    }
    assert!(
        output_collision::ir()
            .unwrap_err()
            .0
            .contains("duplicate output")
    );
    let _ = output_collision(Safe { x: false, y: true });
    #[logic]
    fn bad_bit(input: Bits<3>) -> bool {
        input.bit(3)
    }
    #[logic]
    fn bad_concat(input: Bits<3>) -> Bits<5> {
        input.concat::<3, 5>(input)
    }
    assert!(bad_bit::ir().is_err());
    assert!(bad_concat::ir().is_err());
    let _ = bad_bit;
    let _ = bad_concat;
}

#[test]
fn bounded_folds_preserve_index_and_zero_iteration_semantics() {
    #[logic]
    fn indices(input: Bits<16>) -> Bits<16> {
        input.fold::<256>(|acc, index| acc + bits::<8>(0).concat::<8, 16>(index))
    }
    #[logic]
    fn zero(input: State) -> State {
        input.fold::<0>(|acc, _index| acc)
    }
    let input = State {
        counter: bits(3),
        enabled: true,
    };
    assert_eq!(zero(input), input);
    assert_eq!(
        zero::ir()
            .unwrap()
            .evaluate_typed::<_, State>(input)
            .unwrap(),
        input
    );
    for input in [0, 1, 65535] {
        let expected = (input + 32640) % 65536;
        assert_eq!(indices(bits(input)).get(), expected);
        assert_eq!(
            indices::ir().unwrap().evaluate(&[input]).unwrap(),
            [expected]
        );
    }
}
