use bitlogic::{Bits, bits, logic};

#[logic]
fn select(a: &Bits<3>, b: &Bits<3>, enabled: &bool, output: &mut Bits<3>) {
    *output = *a;
    if *enabled {
        *output = (*a ^ *b) + bits::<3>(1);
    } else {
        *output = (*a + *b) + bits::<3>(1);
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let ir = select::ir()?;
    match std::env::args().nth(1).as_deref() {
        None | Some("verilog") => print!("{}", ir.to_verilog("select_logic")?),
        _ => return Err("expected verilog".into()),
    }
    let mut native = bits::<3>(0);
    select(&bits(2), &bits(3), &true, &mut native);
    assert_eq!(ir.evaluate(&[2, 3, 1])?, [native.get()]);
    Ok(())
}
