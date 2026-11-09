#[cfg(test)]
mod assembler;
#[cfg(test)]
mod composition;
mod core;
#[cfg(test)]
mod isa;
#[cfg(test)]
mod protocols;
#[cfg(test)]
mod reference;
#[cfg(test)]
mod runner;
#[path = "../support/mod.rs"]
mod support;
#[cfg(test)]
mod tests;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    support::no_arguments()?;
    let ir = core::processor_ir()?;
    let core = ir.to_verilog("processor_step")?;
    let top = include_str!("hdl/processor_top.v");
    let pads = include_str!("hdl/pads.v");
    let implementation = format!("{core}\n{top}\n{pads}");
    support::generate(
        "processor_step",
        &ir,
        &[
            ("processor_top.v", top),
            ("pads.v", pads),
            ("implementation.v", &implementation),
            ("processor.mmd", include_str!("hdl/processor.mmd")),
        ],
    )?;
    Ok(())
}
