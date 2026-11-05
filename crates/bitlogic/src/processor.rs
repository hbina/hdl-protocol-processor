//! Bit-blast the value graph into the processor's one-bit truth-table instructions.
use crate::{Binary, Error, Logic, NodeId, Operation, ir::fail};
use protocol_isa::{Instruction, Program};
use std::collections::HashMap;

impl Logic {
    /// Map flattened ports, least significant bit first, to ascending physical pins.
    pub fn to_program(&self) -> Result<Program, Error> {
        let inputs = self
            .inputs
            .iter()
            .map(|p| usize::from(p.width))
            .sum::<usize>();
        let outputs = self
            .outputs
            .iter()
            .map(|p| usize::from(p.width))
            .sum::<usize>();
        if inputs > 8 || outputs > 8 {
            return fail("processor supports at most eight input and eight output bits");
        }
        self.to_program_with_pins(
            &(0..inputs as u8).collect::<Vec<_>>(),
            &(0..outputs as u8).collect::<Vec<_>>(),
        )
    }

    /// Input values are captured once at entry. Outputs are published bit by bit, then HALT.
    /// Integration owns reset/relaunch, input synchronization, and output consumption.
    pub fn to_program_with_pins(&self, inputs: &[u8], outputs: &[u8]) -> Result<Program, Error> {
        if inputs.len()
            != self
                .inputs
                .iter()
                .map(|p| usize::from(p.width))
                .sum::<usize>()
            || outputs.len()
                != self
                    .outputs
                    .iter()
                    .map(|p| usize::from(p.width))
                    .sum::<usize>()
        {
            return fail("processor pin mapping length mismatch");
        }
        if inputs.iter().chain(outputs).any(|p| *p >= 8) {
            return fail("processor pin index must be in 0..8");
        }
        let mut used = 0_u8;
        for pin in outputs {
            if used & (1 << pin) != 0 {
                return fail("processor output pin mappings must be disjoint");
            }
            used |= 1 << pin;
        }
        let mut offset = 0;
        let mut port_bits = Vec::new();
        for port in &self.inputs {
            let end = offset + usize::from(port.width);
            port_bits.push(inputs[offset..end].to_vec());
            offset = end;
        }
        let mut compiler = Compiler {
            logic: self,
            port_bits,
            nodes: HashMap::new(),
            gates: HashMap::new(),
            next: 10,
            instructions: vec![
                Instruction::CaptureInputs,
                Instruction::EvalBit {
                    dst: 8,
                    lhs: 0,
                    rhs: 0,
                    table: 0,
                },
                Instruction::EvalBit {
                    dst: 9,
                    lhs: 0,
                    rhs: 0,
                    table: 15,
                },
            ],
        };
        // Visit reachable nodes in topological order, avoiding deep recursive lowering
        // and avoiding scratch allocation for overwritten/dead assignments.
        let mut live = vec![false; self.nodes.len()];
        let mut pending: Vec<_> = self.outputs.iter().map(|p| p.value).collect();
        while let Some(id) = pending.pop() {
            if live[id.0] {
                continue;
            }
            live[id.0] = true;
            match self.nodes[id.0].operation {
                Operation::Not(a)
                | Operation::Slice { value: a, .. }
                | Operation::Shift { value: a, .. } => pending.push(a),
                Operation::Binary(_, a, b) | Operation::Concat(a, b) => pending.extend([a, b]),
                Operation::Mux { condition, yes, no } => pending.extend([condition, yes, no]),
                Operation::Input(_) | Operation::Constant(_) => {}
            }
        }
        for (index, reachable) in live.into_iter().enumerate() {
            if reachable {
                compiler.node(NodeId(index))?;
            }
        }
        let mut bits = Vec::new();
        for port in &self.outputs {
            bits.extend(compiler.node(port.value)?);
        }
        for (src, pin) in bits.into_iter().zip(outputs.iter().copied()) {
            compiler
                .instructions
                .push(Instruction::WriteBit { src, pin });
        }
        compiler.instructions.push(Instruction::Halt);
        Program::new(compiler.instructions).map_err(|e| Error(e.to_string()))
    }
}

struct Compiler<'a> {
    logic: &'a Logic,
    port_bits: Vec<Vec<u8>>,
    nodes: HashMap<usize, Vec<u8>>,
    gates: HashMap<(u8, u8, u8), u8>,
    next: u8,
    instructions: Vec<Instruction>,
}
impl Compiler<'_> {
    fn gate(&mut self, a: u8, b: u8, table: u8) -> Result<u8, Error> {
        if table == 0 {
            return Ok(8);
        }
        if table == 15 {
            return Ok(9);
        }
        // Reduce gates with constant/identical operands and preserve existing bit registers.
        let possible =
            |av: bool, bv: bool| table & (1 << ((u8::from(av) << 1) | u8::from(bv))) != 0;
        if a == b {
            return match (possible(false, false), possible(true, true)) {
                (false, false) => Ok(8),
                (true, true) => Ok(9),
                (false, true) => Ok(a),
                _ => self.not(a),
            };
        }
        if a == 8 || a == 9 {
            return match (possible(a == 9, false), possible(a == 9, true)) {
                (false, false) => Ok(8),
                (true, true) => Ok(9),
                (false, true) => Ok(b),
                _ => self.not(b),
            };
        }
        if b == 8 || b == 9 {
            return match (possible(false, b == 9), possible(true, b == 9)) {
                (false, false) => Ok(8),
                (true, true) => Ok(9),
                (false, true) => Ok(a),
                _ => self.not(a),
            };
        }
        self.raw_gate(a, b, table)
    }
    fn raw_gate(&mut self, a: u8, b: u8, table: u8) -> Result<u8, Error> {
        if let Some(id) = self.gates.get(&(a, b, table)) {
            return Ok(*id);
        }
        if self.next >= 64 {
            return fail("logic exceeds processor scratch capacity (64 bit registers)");
        }
        let dst = self.next;
        self.next += 1;
        self.instructions.push(Instruction::EvalBit {
            dst,
            lhs: a,
            rhs: b,
            table,
        });
        self.gates.insert((a, b, table), dst);
        Ok(dst)
    }
    fn not(&mut self, a: u8) -> Result<u8, Error> {
        if a == 8 {
            Ok(9)
        } else if a == 9 {
            Ok(8)
        } else {
            self.raw_gate(a, a, 3)
        }
    }
    fn mux(&mut self, c: u8, y: u8, n: u8) -> Result<u8, Error> {
        if c == 8 {
            return Ok(n);
        }
        if c == 9 {
            return Ok(y);
        }
        if y == n {
            return Ok(y);
        }
        let diff = self.gate(y, n, 6)?;
        let masked = self.gate(c, diff, 8)?;
        self.gate(n, masked, 6)
    }
    fn node(&mut self, id: NodeId) -> Result<Vec<u8>, Error> {
        if let Some(bits) = self.nodes.get(&id.0) {
            return Ok(bits.clone());
        }
        let node = &self.logic.nodes[id.0];
        let width = usize::from(node.width);
        let result = match node.operation.clone() {
            Operation::Input(port) => self.port_bits[port].clone(),
            Operation::Constant(value) => (0..width)
                .map(|bit| if value & (1_u64 << bit) == 0 { 8 } else { 9 })
                .collect(),
            Operation::Not(a) => {
                let a = self.node(a)?;
                a.into_iter()
                    .map(|a| self.not(a))
                    .collect::<Result<_, _>>()?
            }
            Operation::Binary(op, a, b) => {
                let a = self.node(a)?;
                let b = self.node(b)?;
                match op {
                    Binary::And | Binary::Or | Binary::Xor => {
                        let table = match op {
                            Binary::And => 8,
                            Binary::Or => 14,
                            _ => 6,
                        };
                        a.into_iter()
                            .zip(b)
                            .map(|(a, b)| self.gate(a, b, table))
                            .collect::<Result<_, _>>()?
                    }
                    Binary::Add | Binary::Sub => {
                        let mut carry = if op == Binary::Sub { 9 } else { 8 };
                        let mut result = Vec::new();
                        for (index, (a, mut b)) in a.into_iter().zip(b).enumerate() {
                            if op == Binary::Sub {
                                b = self.not(b)?;
                            }
                            let sum = self.gate(a, b, 6)?;
                            result.push(self.gate(sum, carry, 6)?);
                            if index + 1 < width {
                                let ab = self.gate(a, b, 8)?;
                                let sc = self.gate(sum, carry, 8)?;
                                carry = self.gate(ab, sc, 14)?;
                            }
                        }
                        result
                    }
                    Binary::Eq | Binary::Ne => {
                        let mut different = 8;
                        for (a, b) in a.into_iter().zip(b) {
                            let bit = self.gate(a, b, 6)?;
                            different = self.gate(different, bit, 14)?;
                        }
                        vec![if op == Binary::Eq {
                            self.not(different)?
                        } else {
                            different
                        }]
                    }
                    Binary::Lt | Binary::Le | Binary::Gt | Binary::Ge => {
                        let (a, b) = if matches!(op, Binary::Gt | Binary::Le) {
                            (b, a)
                        } else {
                            (a, b)
                        };
                        let mut less = 8;
                        for (a, b) in a.into_iter().zip(b) {
                            let different = self.gate(a, b, 6)?;
                            less = self.mux(different, b, less)?;
                        }
                        vec![if matches!(op, Binary::Le | Binary::Ge) {
                            self.not(less)?
                        } else {
                            less
                        }]
                    }
                }
            }
            Operation::Mux { condition, yes, no } => {
                let c = self.node(condition)?[0];
                let yes = self.node(yes)?;
                let no = self.node(no)?;
                yes.into_iter()
                    .zip(no)
                    .map(|(y, n)| self.mux(c, y, n))
                    .collect::<Result<_, _>>()?
            }
            Operation::Slice { value, offset } => {
                self.node(value)?[usize::from(offset)..usize::from(offset) + width].to_vec()
            }
            Operation::Concat(a, b) => {
                let mut result = self.node(b)?;
                result.extend(self.node(a)?);
                result
            }
            Operation::Shift {
                value,
                amount,
                left,
            } => {
                let bits = self.node(value)?;
                (0..width)
                    .map(|index| {
                        let source = if left {
                            index.checked_sub(amount as usize)
                        } else {
                            index.checked_add(amount as usize)
                        };
                        source.and_then(|i| bits.get(i).copied()).unwrap_or(8)
                    })
                    .collect()
            }
        };
        self.nodes.insert(id.0, result.clone());
        Ok(result)
    }
}
