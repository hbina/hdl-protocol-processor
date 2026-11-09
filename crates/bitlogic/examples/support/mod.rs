//! Artifact generation shared by the runnable examples.
use bitlogic::{Logic, Operation};
use std::{error::Error, fmt::Write, fs, path::PathBuf};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

pub fn no_arguments() -> Result<()> {
    if std::env::args_os().len() != 1 {
        return Err("this example accepts no arguments; run it to generate every artifact".into());
    }
    Ok(())
}

/// Keep the directory after successful generation so users can inspect the files.
/// stdout contains only its absolute path, allowing build scripts to consume it.
pub fn generate(module: &str, logic: &Logic, extra_files: &[(&str, &str)]) -> Result<PathBuf> {
    let directory = tempfile::Builder::new()
        .prefix(&format!("bitlogic-{module}-"))
        .tempdir_in("/tmp")?;
    let path = directory.path();
    fs::write(path.join(format!("{module}.v")), logic.to_verilog(module)?)?;
    fs::write(path.join("block.svg"), block_svg(module, logic))?;
    fs::write(path.join("circuit.mmd"), circuit_mermaid(module, logic))?;
    for (name, contents) in extra_files {
        fs::write(path.join(name), contents)?;
    }
    let path = directory.keep();
    println!("{}", path.display());
    Ok(path)
}

fn escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

/// Interface-level diagram; the separate Mermaid file exposes every IR node.
fn block_svg(module: &str, logic: &Logic) -> String {
    let rows = logic.inputs().len().max(logic.outputs().len()).max(1);
    let height = 140 + rows * 36;
    let mut svg = format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 1200 {height}\" role=\"img\" aria-labelledby=\"title description\">\n\
         <title id=\"title\">{} block diagram</title>\n\
         <desc id=\"description\">Combinational module with labeled input and output widths. No clocks or registers. See circuit.mmd for the full expression graph.</desc>\n\
         <defs><marker id=\"arrow\" viewBox=\"0 0 10 10\" refX=\"9\" refY=\"5\" markerWidth=\"7\" markerHeight=\"7\" orient=\"auto-start-reverse\"><path d=\"M 0 0 L 10 5 L 0 10 z\" fill=\"#475569\"/></marker></defs>\n\
         <rect width=\"1200\" height=\"{height}\" fill=\"#f8fafc\"/>\n\
         <g font-family=\"monospace\" font-size=\"16\" fill=\"#0f172a\">\n\
         <text x=\"40\" y=\"35\">{}</text>\n\
         <rect x=\"450\" y=\"65\" width=\"300\" height=\"{}\" rx=\"12\" fill=\"#dbeafe\" stroke=\"#2563eb\"/>\n\
         <text x=\"600\" y=\"{}\" text-anchor=\"middle\">{}</text>\n\
         <text x=\"600\" y=\"{}\" text-anchor=\"middle\">{} IR nodes</text>\n",
        escape(module),
        escape(module),
        height - 100,
        height / 2,
        escape(module),
        height / 2 + 30,
        logic.nodes().len()
    );
    for (ports, input) in [(logic.inputs(), true), (logic.outputs(), false)] {
        for (index, port) in ports.iter().enumerate() {
            let y = 90 + index * 36;
            let (label_x, from, to, prefix) = if input {
                (40, 340, 450, "i")
            } else {
                (870, 750, 860, "o")
            };
            writeln!(svg, "<text x=\"{label_x}\" y=\"{}\">{prefix}_{} [{}]</text><path d=\"M {from} {y} H {to}\" stroke=\"#475569\" stroke-width=\"2\" marker-end=\"url(#arrow)\"/>", y + 5, escape(&port.name), port.width).unwrap();
        }
    }
    svg.push_str("</g></svg>\n");
    svg
}

/// A complete structural graph, including otherwise unused captured nodes.
fn circuit_mermaid(module: &str, logic: &Logic) -> String {
    let mut graph = format!(
        "---\nconfig:\n  maxEdges: 20000\n  maxTextSize: 1000000\n---\nflowchart LR\n  %% {module}: unsigned combinational expression graph; widths in bits\n"
    );
    for (index, node) in logic.nodes().iter().enumerate() {
        let (label, edges): (String, Vec<(_, &str)>) = match node.operation {
            Operation::Input(port) => (format!("i_{}", logic.inputs()[port].name), vec![]),
            Operation::Constant(value) => (format!("constant {value}"), vec![]),
            Operation::Not(a) => ("NOT".into(), vec![(a, "value")]),
            Operation::Binary(op, a, b) => (format!("{op:?}"), vec![(a, "lhs"), (b, "rhs")]),
            Operation::Mux { condition, yes, no } => (
                "MUX".into(),
                vec![(condition, "select"), (yes, "true"), (no, "false")],
            ),
            Operation::Slice { value, offset } => {
                (format!("slice offset {offset}"), vec![(value, "value")])
            }
            Operation::Concat(high, low) => ("concat".into(), vec![(high, "high"), (low, "low")]),
            Operation::Shift {
                value,
                amount,
                left,
            } => (
                format!("shift {} {amount}", if left { "left" } else { "right" }),
                vec![(value, "value")],
            ),
        };
        writeln!(
            graph,
            "  n{index}[\"{} / {} bits\"]",
            escape(&label),
            node.width
        )
        .unwrap();
        for (source, label) in edges {
            writeln!(graph, "  n{} -->|{label}| n{index}", source.index()).unwrap();
        }
    }
    for (index, port) in logic.outputs().iter().enumerate() {
        writeln!(
            graph,
            "  out{index}[\"o_{} / {} bits\"]\n  n{} --> out{index}",
            escape(&port.name),
            port.width,
            port.value.index()
        )
        .unwrap();
    }
    graph
}
