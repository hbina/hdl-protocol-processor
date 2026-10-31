fn main() -> Result<(), Box<dyn std::error::Error>> {
    print!("{}", protocol_processor::emit_verilog()?);
    Ok(())
}
