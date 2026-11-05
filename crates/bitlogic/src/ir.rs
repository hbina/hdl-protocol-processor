use std::{
    error,
    fmt::{self, Write},
};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Error(pub String);
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}
impl error::Error for Error {}
pub(crate) fn fail<T>(message: &str) -> Result<T, Error> {
    Err(Error(message.into()))
}
pub(crate) fn mask(width: u8) -> u64 {
    u64::MAX >> (64 - width)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct NodeId(pub(crate) usize);
impl NodeId {
    pub fn index(self) -> usize {
        self.0
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Binary {
    And,
    Or,
    Xor,
    Add,
    Sub,
    Eq,
    Ne,
    Lt,
    Le,
    Gt,
    Ge,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Operation {
    Input(usize),
    Constant(u64),
    Not(NodeId),
    Binary(Binary, NodeId, NodeId),
    Mux {
        condition: NodeId,
        yes: NodeId,
        no: NodeId,
    },
    Slice {
        value: NodeId,
        offset: u8,
    },
    Concat(NodeId, NodeId),
    Shift {
        value: NodeId,
        amount: u32,
        left: bool,
    },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Node {
    pub width: u8,
    pub operation: Operation,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Port {
    pub name: String,
    pub width: u8,
    pub value: NodeId,
}

/// A DAG of total, deterministic, unsigned bit-vector expressions. No clocks or storage.
#[derive(Clone, Debug)]
pub struct Logic {
    pub(crate) nodes: Vec<Node>,
    pub(crate) inputs: Vec<Port>,
    pub(crate) outputs: Vec<Port>,
}

impl Logic {
    pub fn nodes(&self) -> &[Node] {
        &self.nodes
    }
    pub fn inputs(&self) -> &[Port] {
        &self.inputs
    }
    pub fn outputs(&self) -> &[Port] {
        &self.outputs
    }

    /// Port values are ordered as in the source signature. Out-of-range inputs are errors.
    pub fn evaluate(&self, inputs: &[u64]) -> Result<Vec<u64>, Error> {
        if inputs.len() != self.inputs.len() {
            return fail("input port count mismatch");
        }
        for (port, value) in self.inputs.iter().zip(inputs) {
            if value & !mask(port.width) != 0 {
                return fail("input value exceeds port width");
            }
        }
        let mut values: Vec<u64> = Vec::with_capacity(self.nodes.len());
        for node in &self.nodes {
            let value = match node.operation {
                Operation::Input(index) => inputs[index],
                Operation::Constant(value) => value,
                Operation::Not(a) => !values[a.0],
                Operation::Binary(op, a, b) => {
                    let (a, b) = (values[a.0], values[b.0]);
                    match op {
                        Binary::And => a & b,
                        Binary::Or => a | b,
                        Binary::Xor => a ^ b,
                        Binary::Add => a.wrapping_add(b),
                        Binary::Sub => a.wrapping_sub(b),
                        Binary::Eq => u64::from(a == b),
                        Binary::Ne => u64::from(a != b),
                        Binary::Lt => u64::from(a < b),
                        Binary::Le => u64::from(a <= b),
                        Binary::Gt => u64::from(a > b),
                        Binary::Ge => u64::from(a >= b),
                    }
                }
                Operation::Mux { condition, yes, no } => {
                    values[if values[condition.0] != 0 {
                        yes.0
                    } else {
                        no.0
                    }]
                }
                Operation::Slice { value, offset } => values[value.0] >> offset,
                Operation::Concat(a, b) => (values[a.0] << self.nodes[b.0].width) | values[b.0],
                Operation::Shift {
                    value,
                    amount,
                    left,
                } => if left {
                    values[value.0].checked_shl(amount)
                } else {
                    values[value.0].checked_shr(amount)
                }
                .unwrap_or(0),
            };
            values.push(value & mask(node.width));
        }
        Ok(self.outputs.iter().map(|p| values[p.value.0]).collect())
    }

    /// Compose by port order. All intermediate output widths must match the next inputs.
    pub fn then(&self, next: &Self) -> Result<Self, Error> {
        if self.outputs.len() != next.inputs.len()
            || self
                .outputs
                .iter()
                .zip(&next.inputs)
                .any(|(a, b)| a.width != b.width)
        {
            return fail("composition port widths/count mismatch");
        }
        let mut result = self.clone();
        let mut mapped = Vec::new();
        for node in &next.nodes {
            let id = if let Operation::Input(index) = node.operation {
                self.outputs[index].value
            } else {
                let map = |id: NodeId| mapped[id.0];
                let operation = match node.operation {
                    Operation::Constant(v) => Operation::Constant(v),
                    Operation::Not(a) => Operation::Not(map(a)),
                    Operation::Binary(op, a, b) => Operation::Binary(op, map(a), map(b)),
                    Operation::Mux { condition, yes, no } => Operation::Mux {
                        condition: map(condition),
                        yes: map(yes),
                        no: map(no),
                    },
                    Operation::Slice { value, offset } => Operation::Slice {
                        value: map(value),
                        offset,
                    },
                    Operation::Concat(a, b) => Operation::Concat(map(a), map(b)),
                    Operation::Shift {
                        value,
                        amount,
                        left,
                    } => Operation::Shift {
                        value: map(value),
                        amount,
                        left,
                    },
                    Operation::Input(_) => unreachable!(),
                };
                let id = NodeId(result.nodes.len());
                result.nodes.push(Node {
                    width: node.width,
                    operation,
                });
                id
            };
            mapped.push(id);
        }
        result.outputs = next
            .outputs
            .iter()
            .map(|p| Port {
                value: mapped[p.value.0],
                ..p.clone()
            })
            .collect();
        Ok(result)
    }

    /// Emit portable combinational Verilog. Ports are prefixed with i_ / o_.
    pub fn to_verilog(&self, module: &str) -> Result<String, Error> {
        if !identifier(module) {
            return fail("invalid Verilog module identifier");
        }
        // Prefixing avoids Verilog keywords in Rust parameter names.
        let ports: Vec<_> = self
            .inputs
            .iter()
            .map(|p| format!("input wire [{}:0] i_{}", p.width - 1, p.name))
            .chain(
                self.outputs
                    .iter()
                    .map(|p| format!("output wire [{}:0] o_{}", p.width - 1, p.name)),
            )
            .collect();
        let mut text = format!("module {module}(\n    {}\n);\n", ports.join(",\n    "));
        for (index, node) in self.nodes.iter().enumerate() {
            let expr = match node.operation {
                Operation::Input(p) => format!("i_{}", self.inputs[p].name),
                Operation::Constant(v) => format!("{}'h{:x}", node.width, v),
                Operation::Not(a) => format!("~n{}", a.0),
                Operation::Binary(op, a, b) => {
                    let op = match op {
                        Binary::And => "&",
                        Binary::Or => "|",
                        Binary::Xor => "^",
                        Binary::Add => "+",
                        Binary::Sub => "-",
                        Binary::Eq => "==",
                        Binary::Ne => "!=",
                        Binary::Lt => "<",
                        Binary::Le => "<=",
                        Binary::Gt => ">",
                        Binary::Ge => ">=",
                    };
                    format!("n{} {op} n{}", a.0, b.0)
                }
                Operation::Mux { condition, yes, no } => {
                    format!("n{} ? n{} : n{}", condition.0, yes.0, no.0)
                }
                Operation::Slice { value, offset } => {
                    format!("n{}[{}:{}]", value.0, offset + node.width - 1, offset)
                }
                Operation::Concat(a, b) => format!("{{n{}, n{}}}", a.0, b.0),
                Operation::Shift {
                    value,
                    amount,
                    left,
                } => format!("n{} {} {amount}", value.0, if left { "<<" } else { ">>" }),
            };
            writeln!(
                text,
                "wire [{}:0] n{index};\nassign n{index} = {expr};",
                node.width - 1
            )
            .unwrap();
        }
        for port in &self.outputs {
            writeln!(text, "assign o_{} = n{};", port.name, port.value.0).unwrap();
        }
        text.push_str("endmodule\n");
        Ok(text)
    }
}

fn identifier(name: &str) -> bool {
    let mut chars = name.chars();
    chars
        .next()
        .is_some_and(|c| c.is_ascii_alphabetic() || c == '_')
        && chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
}

/// Checked construction API used by the macro. Prefer `#[logic]` for Rust borrow checking.
#[derive(Default)]
pub struct Builder {
    nodes: Vec<Node>,
    inputs: Vec<Port>,
    outputs: Vec<Port>,
}
impl Builder {
    fn push(&mut self, width: u8, operation: Operation) -> Result<NodeId, Error> {
        if !(1..=64).contains(&width) {
            return fail("bit widths must be in 1..=64");
        }
        if self.nodes.len() >= 65_536 {
            return fail("logic exceeds 65536 expression nodes");
        }
        let id = NodeId(self.nodes.len());
        self.nodes.push(Node { width, operation });
        Ok(id)
    }
    fn width(&self, id: NodeId) -> Result<u8, Error> {
        self.nodes
            .get(id.0)
            .map(|n| n.width)
            .ok_or_else(|| Error("invalid expression reference".into()))
    }
    pub fn input(&mut self, name: &str, width: u8) -> Result<NodeId, Error> {
        if !identifier(name) || self.inputs.iter().any(|p| p.name == name) {
            return fail("invalid or duplicate input name");
        }
        let value = self.push(width, Operation::Input(self.inputs.len()))?;
        self.inputs.push(Port {
            name: name.into(),
            width,
            value,
        });
        Ok(value)
    }
    pub fn constant(&mut self, width: u8, value: u64) -> Result<NodeId, Error> {
        if !(1..=64).contains(&width) {
            return fail("bit widths must be in 1..=64");
        }
        self.push(width, Operation::Constant(value & mask(width)))
    }
    pub fn not(&mut self, a: NodeId) -> Result<NodeId, Error> {
        self.push(self.width(a)?, Operation::Not(a))
    }
    pub fn binary(&mut self, op: Binary, a: NodeId, b: NodeId) -> Result<NodeId, Error> {
        let width = self.width(a)?;
        if width != self.width(b)? {
            return fail("operand width mismatch");
        }
        let result = if matches!(
            op,
            Binary::And | Binary::Or | Binary::Xor | Binary::Add | Binary::Sub
        ) {
            width
        } else {
            1
        };
        self.push(result, Operation::Binary(op, a, b))
    }
    pub fn mux(&mut self, condition: NodeId, yes: NodeId, no: NodeId) -> Result<NodeId, Error> {
        let width = self.width(yes)?;
        if self.width(condition)? != 1 || width != self.width(no)? {
            return fail("mux type mismatch");
        }
        self.push(width, Operation::Mux { condition, yes, no })
    }
    pub fn slice(&mut self, value: NodeId, offset: u8, width: u8) -> Result<NodeId, Error> {
        if width == 0 || u16::from(offset) + u16::from(width) > u16::from(self.width(value)?) {
            return fail("slice out of bounds");
        }
        self.push(width, Operation::Slice { value, offset })
    }
    pub fn concat(&mut self, a: NodeId, b: NodeId) -> Result<NodeId, Error> {
        self.push(self.width(a)? + self.width(b)?, Operation::Concat(a, b))
    }
    pub fn shift(&mut self, value: NodeId, amount: u32, left: bool) -> Result<NodeId, Error> {
        self.push(
            self.width(value)?,
            Operation::Shift {
                value,
                amount,
                left,
            },
        )
    }
    pub fn output(&mut self, name: &str, value: NodeId) -> Result<(), Error> {
        if !identifier(name) || self.outputs.iter().any(|p| p.name == name) {
            return fail("invalid or duplicate output name");
        }
        self.outputs.push(Port {
            name: name.into(),
            width: self.width(value)?,
            value,
        });
        Ok(())
    }
    pub fn finish(self) -> Result<Logic, Error> {
        if self.outputs.is_empty() {
            return fail("logic requires at least one output");
        }
        Ok(Logic {
            nodes: self.nodes,
            inputs: self.inputs,
            outputs: self.outputs,
        })
    }
}
