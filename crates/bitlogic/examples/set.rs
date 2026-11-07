//! A set of keys 0..=7, stored as a membership bitmap.
//!
//! Operations: 0 = contains, 1 = insert, 2 = remove, 3 = clear.
//! `present` reports membership BEFORE the operation; `next` is the updated set.
//! The caller owns storage and feeds `next` back as `current` for later operations.
use bitlogic::{Bits, bits, logic};

#[logic]
fn set_step(
    current: &Bits<8>,
    key: &Bits<3>,
    operation: &Bits<2>,
    next: &mut Bits<8>,
    present: &mut bool,
) {
    // Decode the key using supported constant shifts and bounded expansion.
    let mut candidate = bits::<3>(0);
    let mut mask = bits::<8>(1);
    let mut selected = bits::<8>(0);
    for _ in 0..8 {
        if *key == candidate {
            selected = mask;
        }
        candidate = candidate + bits::<3>(1);
        mask = mask << 1;
    }
    *present = (*current & selected) != bits::<8>(0);
    *next = *current;
    if *operation == bits::<2>(1) {
        *next = *current | selected;
    } else if *operation == bits::<2>(2) {
        *next = *current & !selected;
    } else if *operation == bits::<2>(3) {
        *next = bits::<8>(0);
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    match std::env::args().nth(1).as_deref() {
        Some("verilog") => print!("{}", set_step::ir()?.to_verilog("set_step")?),
        None | Some("demo") => {
            let ir = set_step::ir()?;
            let mut current = bits::<8>(0);
            for (operation, key, label) in [
                (1, 3, "insert"),
                (1, 7, "insert"),
                (1, 3, "insert"),
                (0, 3, "contains"),
                (2, 3, "remove"),
                (2, 3, "remove"),
                (0, 3, "contains"),
                (3, 7, "clear"),
            ] {
                let mut next = bits::<8>(0);
                let mut present = false;
                set_step(
                    &current,
                    &bits(key),
                    &bits(operation),
                    &mut next,
                    &mut present,
                );
                assert_eq!(
                    ir.evaluate(&[current.get(), key, operation])?,
                    [next.get(), u64::from(present)]
                );
                let members: Vec<_> = (0..8).filter(|&value| next.bit(value)).collect();
                println!("{label} {key}: previously present={present}, set={members:?}");
                current = next;
            }
        }
        _ => return Err("expected demo or verilog".into()),
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::BTreeSet, fmt::Write, process::Command};

    // An independent collection-based oracle: no bitmap update expressions.
    fn cases() -> impl Iterator<Item = (u64, u64, u64, u64, bool)> {
        (0..256).flat_map(|current| {
            (0..8).flat_map(move |key| {
                (0..4).map(move |operation| {
                    let mut set: BTreeSet<_> = (0..8)
                        .filter(|value| (current / 2_u64.pow(*value)) % 2 == 1)
                        .collect();
                    let present = set.contains(&(key as u32));
                    match operation {
                        0 => {}
                        1 => {
                            set.insert(key as u32);
                        }
                        2 => {
                            set.remove(&(key as u32));
                        }
                        3 => set.clear(),
                        _ => unreachable!(),
                    }
                    let next = set.into_iter().map(|value| 2_u64.pow(value)).sum();
                    (current, key, operation, next, present)
                })
            })
        })
    }

    #[test]
    fn native_and_ir_exhaustively_match_a_set() {
        let ir = set_step::ir().unwrap();
        for (current, key, operation, expected, was_present) in cases() {
            let mut next = bits::<8>(0);
            let mut present = false;
            set_step(
                &bits(current),
                &bits(key),
                &bits(operation),
                &mut next,
                &mut present,
            );
            assert_eq!((next.get(), present), (expected, was_present));
            assert_eq!(
                ir.evaluate(&[current, key, operation]).unwrap(),
                [expected, u64::from(was_present)]
            );
        }
    }

    #[test]
    fn emitted_hdl_exhaustively_matches_a_set() {
        let mut source = set_step::ir().unwrap().to_verilog("set_step").unwrap();
        source.push_str(
            "module tb; reg [7:0] current; reg [2:0] key; reg [1:0] operation;\n\
             wire [7:0] next; wire present;\n\
             set_step dut(.i_current(current),.i_key(key),.i_operation(operation),\n\
             .o_next(next),.o_present(present));\ninitial begin\n",
        );
        for (current, key, operation, next, present) in cases() {
            writeln!(
                source,
                "current=8'd{current};key=3'd{key};operation=2'd{operation};#1;\
                 if(next!==8'd{next} || present!==1'd{})\
                 $fatal(1,\"set mismatch: state={current} key={key} operation={operation}\");",
                u64::from(present)
            )
            .unwrap();
        }
        source.push_str("$display(\"SET PASS: 8192 cases\");$finish;end endmodule\n");
        let dir = tempfile::tempdir().unwrap();
        let hdl = dir.path().join("set.v");
        let executable = dir.path().join("set.vvp");
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
            output.status.success() && stdout.contains("SET PASS: 8192 cases"),
            "{stdout}\n{}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
}
