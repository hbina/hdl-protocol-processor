//! Structured values and the symbolic values used by generated frontend code.
use crate::{Binary, Bits, Builder, Error, NodeId, bits};
use std::any::{TypeId, type_name};

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Schema {
    Bool,
    Bits(u8),
    Struct {
        identity: TypeId,
        name: &'static str,
        fields: Vec<(String, Schema)>,
    },
}

impl Schema {
    pub fn structure<T: 'static>(fields: Vec<(String, Schema)>) -> Self {
        Self::Struct {
            identity: TypeId::of::<T>(),
            name: type_name::<T>(),
            fields,
        }
    }

    pub fn leaves(&self) -> Vec<(String, Schema)> {
        fn visit(schema: &Schema, path: String, result: &mut Vec<(String, Schema)>) {
            match schema {
                Schema::Struct { fields, .. } => {
                    for (name, child) in fields {
                        let path = if path.is_empty() {
                            name.clone()
                        } else {
                            format!("{path}.{name}")
                        };
                        visit(child, path, result);
                    }
                }
                _ => result.push((path, schema.clone())),
            }
        }
        let mut result = Vec::new();
        visit(self, String::new(), &mut result);
        result
    }

    pub fn width(&self) -> Result<u8, Error> {
        match self {
            Self::Bool => Ok(1),
            Self::Bits(n) if (1..=64).contains(n) => Ok(*n),
            _ => Err(Error("expected bool or Bits<1..=64> leaf".into())),
        }
    }
}

/// Native aggregate layout. Derive this trait for named, non-generic structs.
pub trait LogicValue: Sized + 'static {
    fn schema() -> Schema;
    fn flatten(&self) -> Vec<u64>;
    fn read(values: &mut impl Iterator<Item = u64>) -> Result<Self, Error>;

    fn from_values(values: &[u64]) -> Result<Self, Error> {
        let mut values = values.iter().copied();
        let value = Self::read(&mut values)?;
        if values.next().is_some() {
            return Err(Error("too many value leaves".into()));
        }
        Ok(value)
    }

    /// Unroll a bounded pure recurrence. The index is 0 through N-1.
    fn fold<const N: usize>(self, f: impl Fn(Self, Bits<8>) -> Self) -> Self {
        assert!(N <= 256, "fold is limited to 256 iterations");
        (0..N).fold(self, |acc, index| f(acc, bits(index as u64)))
    }
}

impl LogicValue for bool {
    fn schema() -> Schema {
        Schema::Bool
    }
    fn flatten(&self) -> Vec<u64> {
        vec![u64::from(*self)]
    }
    fn read(values: &mut impl Iterator<Item = u64>) -> Result<Self, Error> {
        match values.next() {
            Some(0) => Ok(false),
            Some(1) => Ok(true),
            _ => Err(Error("expected boolean value leaf".into())),
        }
    }
}

impl<const N: usize> LogicValue for Bits<N> {
    fn schema() -> Schema {
        Schema::Bits(u8::try_from(N).unwrap_or(0))
    }
    fn flatten(&self) -> Vec<u64> {
        vec![self.get()]
    }
    fn read(values: &mut impl Iterator<Item = u64>) -> Result<Self, Error> {
        let width = Self::schema().width()?;
        let value = values
            .next()
            .ok_or_else(|| Error("missing value leaf".into()))?;
        if value & !(u64::MAX >> (64 - width)) != 0 {
            return Err(Error("value exceeds leaf width".into()));
        }
        Ok(bits(value))
    }
}

/// An aggregate of scalar DAG values. Used by generated code, not hardware storage.
#[doc(hidden)]
#[derive(Clone, Debug)]
pub struct Symbolic {
    pub schema: Schema,
    pub values: Vec<NodeId>,
}

impl Symbolic {
    pub fn input<T: LogicValue>(builder: &mut Builder, root: &str) -> Result<Self, Error> {
        let schema = T::schema();
        let mut values = Vec::new();
        for (path, leaf) in schema.leaves() {
            let name = if path.is_empty() {
                root.to_owned()
            } else {
                path.replace('.', "_")
            };
            values.push(builder.input(&name, leaf.width()?)?);
        }
        Ok(Self { schema, values })
    }
    pub fn constant<T: LogicValue>(builder: &mut Builder, value: T) -> Result<Self, Error> {
        let schema = T::schema();
        let values = schema
            .leaves()
            .iter()
            .zip(value.flatten())
            .map(|((_, leaf), value)| builder.constant(leaf.width()?, value))
            .collect::<Result<_, _>>()?;
        Ok(Self { schema, values })
    }
    pub fn field(&self, name: &str) -> Result<Self, Error> {
        if let Schema::Struct { fields, .. } = &self.schema {
            let mut offset = 0;
            for (field, schema) in fields {
                let count = schema.leaves().len();
                if field == name {
                    return Ok(Self {
                        schema: schema.clone(),
                        values: self.values[offset..offset + count].to_vec(),
                    });
                }
                offset += count;
            }
        }
        Err(Error(format!("unknown aggregate field {name}")))
    }
    pub fn structure<T: LogicValue>(fields: Vec<(&str, Self)>) -> Result<Self, Error> {
        let schema = T::schema();
        let Schema::Struct {
            fields: expected, ..
        } = &schema
        else {
            return Err(Error("expected struct type".into()));
        };
        if expected.len() != fields.len() {
            return Err(Error("incomplete struct value".into()));
        }
        let mut values = Vec::new();
        for (name, ty) in expected {
            let matches: Vec<_> = fields.iter().filter(|(n, _)| n == name).collect();
            if matches.len() != 1 || matches[0].1.schema != *ty {
                return Err(Error(format!(
                    "struct field {name} type/definition mismatch"
                )));
            }
            values.extend(&matches[0].1.values);
        }
        Ok(Self { schema, values })
    }
    pub fn require<T: LogicValue>(&self) -> Result<(), Error> {
        if self.schema != T::schema() {
            return Err(Error("logical value type mismatch".into()));
        }
        Ok(())
    }
    fn scalar(&self) -> Result<NodeId, Error> {
        self.schema.width()?;
        self.values
            .first()
            .copied()
            .ok_or_else(|| Error("missing scalar node".into()))
    }
    pub fn not(&self, builder: &mut Builder) -> Result<Self, Error> {
        Ok(Self {
            schema: self.schema.clone(),
            values: vec![builder.not(self.scalar()?)?],
        })
    }
    pub fn binary(
        &self,
        builder: &mut Builder,
        op: Binary,
        rhs: &Self,
        logical: bool,
    ) -> Result<Self, Error> {
        if self.schema != rhs.schema {
            return Err(Error("binary logical type mismatch".into()));
        }
        if logical && self.schema != Schema::Bool {
            return Err(Error("logical operators require bool".into()));
        }
        if matches!(op, Binary::Add | Binary::Sub) && self.schema == Schema::Bool {
            return Err(Error("arithmetic requires Bits<N>".into()));
        }
        let comparison = matches!(
            op,
            Binary::Eq | Binary::Ne | Binary::Lt | Binary::Le | Binary::Gt | Binary::Ge
        );
        let value = builder.binary(op, self.scalar()?, rhs.scalar()?)?;
        Ok(Self {
            schema: if comparison {
                Schema::Bool
            } else {
                self.schema.clone()
            },
            values: vec![value],
        })
    }
    pub fn mux(
        builder: &mut Builder,
        condition: &Self,
        yes: &Self,
        no: &Self,
    ) -> Result<Self, Error> {
        condition.require::<bool>()?;
        if yes.schema != no.schema {
            return Err(Error("conditional branch type mismatch".into()));
        }
        let values = yes
            .values
            .iter()
            .zip(&no.values)
            .map(|(&y, &n)| builder.mux(condition.scalar()?, y, n))
            .collect::<Result<_, _>>()?;
        Ok(Self {
            schema: yes.schema.clone(),
            values,
        })
    }
    pub fn shift(&self, builder: &mut Builder, amount: u32, left: bool) -> Result<Self, Error> {
        if !matches!(self.schema, Schema::Bits(_)) {
            return Err(Error("shifts require Bits<N>".into()));
        }
        Ok(Self {
            schema: self.schema.clone(),
            values: vec![builder.shift(self.scalar()?, amount, left)?],
        })
    }
    pub fn slice(
        &self,
        builder: &mut Builder,
        offset: u8,
        width: u8,
        bit: bool,
    ) -> Result<Self, Error> {
        if !matches!(self.schema, Schema::Bits(_)) {
            return Err(Error("bit methods require Bits<N>".into()));
        }
        Ok(Self {
            schema: if bit {
                Schema::Bool
            } else {
                Schema::Bits(width)
            },
            values: vec![builder.slice(self.scalar()?, offset, width)?],
        })
    }
    pub fn concat(
        &self,
        builder: &mut Builder,
        rhs: &Self,
        low: u8,
        total: u8,
    ) -> Result<Self, Error> {
        let Schema::Bits(high) = self.schema else {
            return Err(Error("concat requires Bits<N>".into()));
        };
        if rhs.schema != Schema::Bits(low) || u16::from(high) + u16::from(low) != u16::from(total) {
            return Err(Error("concatenation width mismatch".into()));
        }
        Ok(Self {
            schema: Schema::Bits(total),
            values: vec![builder.concat(self.scalar()?, rhs.scalar()?)?],
        })
    }
    pub fn output(&self, builder: &mut Builder) -> Result<(), Error> {
        for ((path, _), &value) in self.schema.leaves().iter().zip(&self.values) {
            let name = if path.is_empty() {
                "result".into()
            } else {
                path.replace('.', "_")
            };
            builder.output(&name, value)?;
        }
        Ok(())
    }
}
