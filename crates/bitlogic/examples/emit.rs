use bitlogic::{Bits, LogicValue, bits, logic};

#[derive(Clone, Copy, LogicValue)]
struct Inputs {
    a: Bits<3>,
    b: Bits<3>,
    enabled: bool,
}

#[logic]
fn select(input: Inputs) -> Bits<3> {
    if input.enabled {
        (input.a ^ input.b) + bits::<3>(1)
    } else {
        (input.a + input.b) + bits::<3>(1)
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let ir = select::ir()?;
    match std::env::args().nth(1).as_deref() {
        None | Some("verilog") => print!("{}", ir.to_verilog("select_logic")?),
        _ => return Err("expected verilog".into()),
    }
    let input = Inputs {
        a: bits(2),
        b: bits(3),
        enabled: true,
    };
    assert_eq!(ir.evaluate_typed::<_, Bits<3>>(input)?, select(input));
    Ok(())
}
