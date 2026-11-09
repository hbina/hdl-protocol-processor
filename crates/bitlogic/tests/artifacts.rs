//! Check the exported interface and circuit connectivity against a small fixture.
#[allow(dead_code)]
#[path = "../examples/support/mod.rs"]
mod artifacts;

use bitlogic::Builder;
use std::fs;

#[test]
fn artifact_bundles_are_persistent_unique_and_connected() {
    let mut builder = Builder::default();
    let input = builder.input("data", 8).unwrap();
    let enable = builder.input("enable", 1).unwrap();
    let zero = builder.constant(8, 0).unwrap();
    let selected = builder.mux(enable, input, zero).unwrap();
    builder.output("result", selected).unwrap();
    // An alias must connect to its actual source rather than an invented node.
    builder.output("original", input).unwrap();
    let logic = builder.finish().unwrap();
    let first = artifacts::generate("fixture", &logic, &[("extra.txt", "retained")]).unwrap();
    let second = artifacts::generate("fixture", &logic, &[]).unwrap();
    assert_ne!(first, second);
    for path in [&first, &second] {
        assert_eq!(path.parent().unwrap(), std::path::Path::new("/tmp"));
        assert_eq!(
            fs::read_to_string(path.join("fixture.v")).unwrap(),
            logic.to_verilog("fixture").unwrap()
        );
        let svg = fs::read_to_string(path.join("block.svg")).unwrap();
        assert!(svg.contains("i_data [8]"));
        assert!(svg.contains("o_result [8]"));
        let circuit = fs::read_to_string(path.join("circuit.mmd")).unwrap();
        for connection in [
            "n1 -->|select| n3",
            "n0 -->|true| n3",
            "n2 -->|false| n3",
            "n3 --> out0",
            "n0 --> out1",
        ] {
            assert!(circuit.contains(connection), "missing {connection}");
        }
    }
    assert_eq!(
        fs::read_to_string(first.join("extra.txt")).unwrap(),
        "retained"
    );
    fs::remove_dir_all(first).unwrap();
    fs::remove_dir_all(second).unwrap();
}
