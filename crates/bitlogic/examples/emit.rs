use bitlogic::{Bits, LogicValue, bits, logic};

#[derive(Clone, Copy, LogicValue)]
struct Inputs {
    a: Bits<3>,
    b: Bits<3>,
    enabled: bool,
}

#[logic]
#[allow(
    dead_code,
    reason = "Artifact export uses the IR; native evaluation remains available to tests."
)]
fn select(input: Inputs) -> Bits<3> {
    if input.enabled {
        (input.a ^ input.b) + bits::<3>(1)
    } else {
        (input.a + input.b) + bits::<3>(1)
    }
}

mod support;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    support::no_arguments()?;
    support::generate("select_logic", &select::ir()?, &[])?;
    Ok(())
}
