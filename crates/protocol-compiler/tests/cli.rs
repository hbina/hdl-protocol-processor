use std::process::Command;

#[test]
fn cli_emits_compiled_program_and_rejects_invalid_parameters() {
    let exe = env!("CARGO_BIN_EXE_protocol-compiler");
    let output = Command::new(exe)
        .args([
            "uart-tx",
            "--pin",
            "0",
            "--cycles-per-bit",
            "8",
            "--text",
            "Hi",
        ])
        .output()
        .unwrap();
    assert!(output.status.success());
    assert!(output.stderr.is_empty());
    let words = String::from_utf8(output.stdout).unwrap();
    assert_eq!(words.lines().count(), 43);
    assert_eq!(words.lines().last(), Some("f0000000"));
    let assembly = Command::new(exe)
        .args([
            "uart-tx",
            "--pin",
            "0",
            "--cycles-per-bit",
            "8",
            "--text",
            "Hi",
            "--format",
            "asm",
        ])
        .output()
        .unwrap();
    assert!(assembly.status.success());
    let assembly = String::from_utf8(assembly.stdout).unwrap();
    assert_eq!(assembly.lines().count(), 43);
    assert_eq!(assembly.lines().next(), Some("000: SET_PINS 0x01, 0x01"));
    assert!(assembly.ends_with("02a: HALT\n"));
    for (pin, period) in [("8", "8"), ("0", "0"), ("0", "65536")] {
        let invalid = Command::new(exe)
            .args([
                "uart-tx",
                "--pin",
                pin,
                "--cycles-per-bit",
                period,
                "--text",
                "Hi",
            ])
            .output()
            .unwrap();
        assert_eq!(invalid.status.code(), Some(2));
        assert!(invalid.stdout.is_empty());
        assert!(!invalid.stderr.is_empty());
    }
}
