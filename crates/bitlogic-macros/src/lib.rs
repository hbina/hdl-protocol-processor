//! Capture a deliberately restricted, borrow-checked Rust function as untimed logic.
use proc_macro::TokenStream;
use proc_macro2::TokenStream as Tokens;
use quote::{format_ident, quote};
use std::collections::BTreeMap;
use syn::{Expr, FnArg, GenericArgument, ItemFn, Pat, PathArguments, Stmt, Type, spanned::Spanned};

#[proc_macro_attribute]
pub fn logic(attribute: TokenStream, item: TokenStream) -> TokenStream {
    if !attribute.is_empty() {
        return syn::Error::new(
            proc_macro2::Span::call_site(),
            "#[logic] takes no arguments",
        )
        .into_compile_error()
        .into();
    }
    match syn::parse::<ItemFn>(item).and_then(expand) {
        Ok(t) => t.into(),
        Err(e) => e.into_compile_error().into(),
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Kind {
    Bool,
    Bits(u8),
}
impl Kind {
    fn width(self) -> u8 {
        match self {
            Self::Bool => 1,
            Self::Bits(n) => n,
        }
    }
}
#[derive(Clone)]
struct Value {
    id: syn::Ident,
    kind: Kind,
}
#[derive(Clone)]
struct Variable {
    value: Option<Value>,
    kind: Kind,
    parameter: bool,
    mutable: bool,
}
type Env = BTreeMap<String, Variable>;
#[derive(Default)]
struct Lower {
    statements: Vec<Tokens>,
    serial: usize,
    work: usize,
}
fn error(node: impl Spanned, message: &str) -> syn::Error {
    syn::Error::new(node.span(), message)
}
fn integer(expr: &Expr) -> syn::Result<u64> {
    if let Expr::Lit(lit) = expr
        && let syn::Lit::Int(n) = &lit.lit
    {
        return n.base10_parse();
    }
    Err(error(expr, "expected an unsigned integer literal"))
}
fn kind(ty: &Type) -> syn::Result<Kind> {
    if let Type::Path(path) = ty {
        if path.path.is_ident("bool") {
            return Ok(Kind::Bool);
        }
        if let Some(last) = path.path.segments.last()
            && last.ident == "Bits"
            && let PathArguments::AngleBracketed(args) = &last.arguments
            && args.args.len() == 1
            && let GenericArgument::Const(expr) = &args.args[0]
        {
            let n = integer(expr)?;
            if (1..=64).contains(&n) {
                return Ok(Kind::Bits(n as u8));
            }
        }
    }
    Err(error(
        ty,
        "expected bool or Bits<N>, with literal N in 1..=64",
    ))
}

fn expand(function: ItemFn) -> syn::Result<Tokens> {
    let sig = &function.sig;
    if sig.asyncness.is_some()
        || sig.constness.is_some()
        || sig.unsafety.is_some()
        || sig.abi.is_some()
        || sig.variadic.is_some()
        || !sig.generics.params.is_empty()
        || sig.generics.where_clause.is_some()
        || !matches!(sig.output, syn::ReturnType::Default)
    {
        return Err(error(
            sig,
            "logic functions must be ordinary, non-generic functions returning unit",
        ));
    }
    let mut lower = Lower::default();
    let mut env = Env::new();
    let mut outputs = Vec::new();
    for arg in &sig.inputs {
        let FnArg::Typed(arg) = arg else {
            return Err(error(arg, "logic functions cannot have receivers"));
        };
        let Pat::Ident(binding) = &*arg.pat else {
            return Err(error(arg, "expected a named port"));
        };
        if binding.by_ref.is_some() || binding.mutability.is_some() || binding.subpat.is_some() {
            return Err(error(binding, "use a simple parameter binding"));
        }
        let Type::Reference(reference) = &*arg.ty else {
            return Err(error(
                arg,
                "ports must be borrowed: &Bits<N>, &bool, or mutable references",
            ));
        };
        let ty = kind(&reference.elem)?;
        let name = binding.ident.to_string();
        let name = name.strip_prefix("r#").unwrap_or(&name).to_string();
        let mutable = reference.mutability.is_some();
        let value = if mutable {
            outputs.push(name.clone());
            None
        } else {
            let width = ty.width();
            Some(lower.emit(ty, quote!(__logic_builder.input(#name,#width)?)))
        };
        env.insert(
            name,
            Variable {
                value,
                kind: ty,
                parameter: true,
                mutable,
            },
        );
    }
    lower.block(&function.block, &mut env)?;
    for name in outputs {
        let Some(value) = &env[&name].value else {
            return Err(error(
                sig,
                &format!("output {name} is not assigned on every path"),
            ));
        };
        let id = &value.id;
        lower
            .statements
            .push(quote!(__logic_builder.output(#name,#id)?;));
    }
    let name = &sig.ident;
    let vis = &function.vis;
    let statements = lower.statements;
    Ok(quote! {
        #function
        #[allow(non_camel_case_types)]
        #vis struct #name {}
        impl #name {
            /// Capture all input-dependent paths as an untimed, typed expression graph.
            pub fn ir()->::std::result::Result<::bitlogic::Logic,::bitlogic::Error> {
                let mut __logic_builder=::bitlogic::Builder::default();
                #(#statements)*
                __logic_builder.finish()
            }
        }
    })
}

impl Lower {
    fn emit(&mut self, kind: Kind, expr: Tokens) -> Value {
        let id = format_ident!("__logic_value_{}", self.serial);
        self.serial += 1;
        self.statements.push(quote!(let #id=#expr;));
        Value { id, kind }
    }
    fn require(&self, value: &Value, expected: Kind, expr: &Expr) -> syn::Result<()> {
        if value.kind != expected {
            return Err(error(expr, "logic type/width mismatch"));
        }
        Ok(())
    }
    fn read(&self, name: &syn::Ident, env: &Env, parameter: bool) -> syn::Result<Value> {
        let key = name.to_string();
        let key = key.strip_prefix("r#").unwrap_or(&key);
        let var = env
            .get(key)
            .ok_or_else(|| error(name, "unknown logic variable"))?;
        if var.parameter != parameter {
            return Err(error(name, "dereference ports; use local values directly"));
        }
        var.value
            .clone()
            .ok_or_else(|| error(name, "output read before assignment on every path"))
    }
    fn expr(&mut self, expr: &Expr, env: &Env) -> syn::Result<Value> {
        self.work += 1;
        if self.work > 65_536 {
            return Err(error(expr, "logic exceeds 65536 lowering steps"));
        }
        match expr {
            Expr::Paren(p) => self.expr(&p.expr, env),
            Expr::Group(g) => self.expr(&g.expr, env),
            Expr::Path(p) if p.path.get_ident().is_some() => {
                self.read(p.path.get_ident().unwrap(), env, false)
            }
            Expr::Lit(lit) if matches!(lit.lit, syn::Lit::Bool(_)) => {
                let syn::Lit::Bool(b) = &lit.lit else {
                    unreachable!()
                };
                let n = u64::from(b.value);
                Ok(self.emit(Kind::Bool, quote!(__logic_builder.constant(1,#n)?)))
            }
            Expr::Unary(u) => match &u.op {
                syn::UnOp::Deref(_) => {
                    if let Expr::Path(p) = &*u.expr
                        && let Some(name) = p.path.get_ident()
                    {
                        self.read(name, env, true)
                    } else {
                        Err(error(u, "only named ports may be dereferenced"))
                    }
                }
                syn::UnOp::Not(_) => {
                    let a = self.expr(&u.expr, env)?;
                    let id = &a.id;
                    Ok(self.emit(a.kind, quote!(__logic_builder.not(#id)?)))
                }
                _ => Err(error(u, "unsupported unary operation")),
            },
            Expr::Binary(b) => {
                let a = self.expr(&b.left, env)?;
                if matches!(b.op, syn::BinOp::Shl(_) | syn::BinOp::Shr(_)) {
                    if matches!(a.kind, Kind::Bool) {
                        return Err(error(b, "shifts require Bits<N>"));
                    }
                    let amount = u32::try_from(integer(&b.right)?)
                        .map_err(|_| error(b, "shift literal exceeds u32"))?;
                    let left = matches!(b.op, syn::BinOp::Shl(_));
                    let id = &a.id;
                    return Ok(self.emit(a.kind, quote!(__logic_builder.shift(#id,#amount,#left)?)));
                }
                let rhs = self.expr(&b.right, env)?;
                self.require(&rhs, a.kind, &b.right)?;
                let (op, comparison) = match b.op {
                    syn::BinOp::BitAnd(_) => ("And", false),
                    syn::BinOp::BitOr(_) => ("Or", false),
                    syn::BinOp::BitXor(_) => ("Xor", false),
                    syn::BinOp::And(_) => ("And", false),
                    syn::BinOp::Or(_) => ("Or", false),
                    syn::BinOp::Add(_) => ("Add", false),
                    syn::BinOp::Sub(_) => ("Sub", false),
                    syn::BinOp::Eq(_) => ("Eq", true),
                    syn::BinOp::Ne(_) => ("Ne", true),
                    syn::BinOp::Lt(_) => ("Lt", true),
                    syn::BinOp::Le(_) => ("Le", true),
                    syn::BinOp::Gt(_) => ("Gt", true),
                    syn::BinOp::Ge(_) => ("Ge", true),
                    _ => {
                        return Err(error(
                            b,
                            "unsupported binary operation or compound assignment",
                        ));
                    }
                };
                if matches!(b.op, syn::BinOp::And(_) | syn::BinOp::Or(_)) && a.kind != Kind::Bool {
                    return Err(error(b, "logical operators require bool"));
                }
                if matches!(b.op, syn::BinOp::Add(_) | syn::BinOp::Sub(_)) && a.kind == Kind::Bool {
                    return Err(error(b, "arithmetic requires Bits<N>"));
                }
                let op = format_ident!("{op}");
                let kind = if comparison { Kind::Bool } else { a.kind };
                let (a, b) = (&a.id, &rhs.id);
                Ok(self.emit(
                    kind,
                    quote!(__logic_builder.binary(::bitlogic::Binary::#op,#a,#b)?),
                ))
            }
            Expr::Call(call) => {
                let Expr::Path(path) = &*call.func else {
                    return Err(error(call, "only bits::<N>(literal) calls are supported"));
                };
                let last = path.path.segments.last().unwrap();
                if last.ident != "bits" || call.args.len() != 1 {
                    return Err(error(
                        call,
                        "only bits::<N>(literal) calls are supported; compose captured IR with then()",
                    ));
                }
                let widths = generic_integers(&last.arguments)?;
                if widths.len() != 1 || !(1..=64).contains(&widths[0]) {
                    return Err(error(call, "bits requires one width in 1..=64"));
                }
                let n = widths[0] as u8;
                let value = integer(&call.args[0])?;
                Ok(self.emit(Kind::Bits(n), quote!(__logic_builder.constant(#n,#value)?)))
            }
            Expr::MethodCall(call) => {
                let a = if let Expr::Path(path) = &*call.receiver
                    && let Some(name) = path.path.get_ident()
                    && env.get(&name.to_string()).is_some_and(|v| v.parameter)
                {
                    self.read(name, env, true)?
                } else {
                    self.expr(&call.receiver, env)?
                };
                let Kind::Bits(n) = a.kind else {
                    return Err(error(call, "bit methods require Bits<N>"));
                };
                let generic = call
                    .turbofish
                    .as_ref()
                    .map(|g| generic_integers(&PathArguments::AngleBracketed(g.clone())))
                    .transpose()?
                    .unwrap_or_default();
                let id = &a.id;
                match call.method.to_string().as_str() {
                    "bit" | "slice" if call.args.len() == 1 => {
                        let offset = integer(&call.args[0])?;
                        let width = if call.method == "bit" && generic.is_empty() {
                            1
                        } else if call.method == "slice" && generic.len() == 1 {
                            generic[0]
                        } else {
                            return Err(error(call, "use bit(index) or slice::<N>(offset)"));
                        };
                        if width == 0
                            || offset
                                .checked_add(width)
                                .is_none_or(|end| end > u64::from(n))
                        {
                            return Err(error(call, "slice out of bounds"));
                        }
                        let ty = if call.method == "bit" {
                            Kind::Bool
                        } else {
                            Kind::Bits(width as u8)
                        };
                        let (offset, width) = (offset as u8, width as u8);
                        Ok(self.emit(ty, quote!(__logic_builder.slice(#id,#offset,#width)?)))
                    }
                    "concat" if call.args.len() == 1 && generic.len() == 2 => {
                        let b = self.expr(&call.args[0], env)?;
                        let Kind::Bits(m) = b.kind else {
                            return Err(error(call, "concat requires Bits<N>"));
                        };
                        let width = u64::from(n) + u64::from(m);
                        if generic[0] != u64::from(m) || generic[1] != width || width > 64 {
                            return Err(error(call, "concatenation width mismatch"));
                        }
                        let b = &b.id;
                        Ok(self.emit(
                            Kind::Bits(width as u8),
                            quote!(__logic_builder.concat(#id,#b)?),
                        ))
                    }
                    _ => Err(error(
                        call,
                        "supported methods: bit(index), slice::<N>(offset), concat::<M,O>(rhs)",
                    )),
                }
            }
            Expr::If(branch) => {
                let condition = self.expr(&branch.cond, env)?;
                self.require(&condition, Kind::Bool, &branch.cond)?;
                let yes = self.value_block(&branch.then_branch, env)?;
                let Some((_, otherwise)) = &branch.else_branch else {
                    return Err(error(branch, "value conditionals require else"));
                };
                let no = if let Expr::Block(block) = &**otherwise {
                    self.value_block(&block.block, env)?
                } else {
                    self.expr(otherwise, env)?
                };
                self.require(&no, yes.kind, otherwise)?;
                let (c, y, n) = (&condition.id, &yes.id, &no.id);
                Ok(self.emit(yes.kind, quote!(__logic_builder.mux(#c,#y,#n)?)))
            }
            _ => Err(error(expr, "unsupported logic expression")),
        }
    }
    fn value_block(&mut self, block: &syn::Block, env: &Env) -> syn::Result<Value> {
        let mut env = env.clone();
        let Some((last, initial)) = block.stmts.split_last() else {
            return Err(error(block, "expected a value expression"));
        };
        for stmt in initial {
            if !matches!(stmt, Stmt::Local(_)) {
                return Err(error(
                    stmt,
                    "value blocks allow local declarations and a trailing expression only",
                ));
            }
            self.statement(stmt, &mut env)?;
        }
        let Stmt::Expr(expr, None) = last else {
            return Err(error(last, "expected a trailing value expression"));
        };
        self.expr(expr, &env)
    }
    fn block(&mut self, block: &syn::Block, env: &mut Env) -> syn::Result<()> {
        // Locals belong to this scope; assignments to existing bindings propagate.
        let original = env.keys().cloned().collect::<Vec<_>>();
        for stmt in &block.stmts {
            self.statement(stmt, env)?;
        }
        env.retain(|name, _| original.contains(name));
        Ok(())
    }
    fn statement(&mut self, stmt: &Stmt, env: &mut Env) -> syn::Result<()> {
        self.work += 1;
        if self.work > 65_536 {
            return Err(error(stmt, "logic exceeds 65536 lowering steps"));
        }
        match stmt {
            Stmt::Local(local) => {
                let (pat, annotation) = if let Pat::Type(p) = &local.pat {
                    (&*p.pat, Some(kind(&p.ty)?))
                } else {
                    (&local.pat, None)
                };
                let Pat::Ident(binding) = pat else {
                    return Err(error(pat, "use a named local binding"));
                };
                if binding.by_ref.is_some() || binding.subpat.is_some() {
                    return Err(error(
                        pat,
                        "reference aliases and patterns are not supported",
                    ));
                }
                let name = binding.ident.to_string();
                if env.contains_key(&name) {
                    return Err(error(pat, "logic local shadowing is not supported"));
                }
                let Some(init) = &local.init else {
                    return Err(error(local, "local bindings require an initializer"));
                };
                if init.diverge.is_some() {
                    return Err(error(local, "let-else is not supported"));
                }
                let value = self.expr(&init.expr, env)?;
                if let Some(expected) = annotation {
                    self.require(&value, expected, &init.expr)?;
                }
                env.insert(
                    name,
                    Variable {
                        kind: value.kind,
                        value: Some(value),
                        parameter: false,
                        mutable: binding.mutability.is_some(),
                    },
                );
                Ok(())
            }
            Stmt::Expr(Expr::Assign(assign), _) => {
                let (target, parameter) = match &*assign.left {
                    Expr::Path(path) => (path.path.get_ident(), false),
                    Expr::Unary(u) if matches!(u.op, syn::UnOp::Deref(_)) => {
                        if let Expr::Path(path) = &*u.expr {
                            (path.path.get_ident(), true)
                        } else {
                            (None, true)
                        }
                    }
                    _ => (None, false),
                };
                let Some(target) = target else {
                    return Err(error(
                        assign,
                        "assign to a named local or dereferenced output",
                    ));
                };
                let key = target.to_string();
                let key = key.strip_prefix("r#").unwrap_or(&key);
                let var = env
                    .get(key)
                    .ok_or_else(|| error(target, "unknown assignment target"))?;
                if !var.mutable || var.parameter != parameter {
                    return Err(error(
                        target,
                        "assignment requires a mutable local or dereferenced output",
                    ));
                }
                let expected = var.kind;
                let value = self.expr(&assign.right, env)?;
                self.require(&value, expected, &assign.right)?;
                env.get_mut(key).unwrap().value = Some(value);
                Ok(())
            }
            Stmt::Expr(Expr::If(branch), _) => {
                let condition = self.expr(&branch.cond, env)?;
                self.require(&condition, Kind::Bool, &branch.cond)?;
                let mut yes = env.clone();
                self.block(&branch.then_branch, &mut yes)?;
                let mut no = env.clone();
                if let Some((_, otherwise)) = &branch.else_branch {
                    match &**otherwise {
                        Expr::Block(b) => self.block(&b.block, &mut no)?,
                        Expr::If(_) => {
                            self.statement(&Stmt::Expr((**otherwise).clone(), None), &mut no)?
                        }
                        _ => return Err(error(otherwise, "expected else block")),
                    }
                }
                for (name, var) in env.iter_mut() {
                    var.value = match (&yes[name].value, &no[name].value) {
                        (Some(y), Some(n)) if y.id == n.id => Some(y.clone()),
                        (Some(y), Some(n)) => {
                            let (c, y, n) = (&condition.id, &y.id, &n.id);
                            Some(self.emit(var.kind, quote!(__logic_builder.mux(#c,#y,#n)?)))
                        }
                        _ => None,
                    };
                }
                Ok(())
            }
            Stmt::Expr(Expr::Block(block), _) => self.block(&block.block, env),
            Stmt::Expr(Expr::ForLoop(loop_), _) => {
                if loop_.label.is_some() || !matches!(&*loop_.pat, Pat::Wild(_)) {
                    return Err(error(
                        loop_,
                        "use for _ in literal..literal; indexed loops are not supported",
                    ));
                }
                let Expr::Range(range) = &*loop_.expr else {
                    return Err(error(loop_, "expected a literal loop range"));
                };
                let (Some(start), Some(end)) = (&range.start, &range.end) else {
                    return Err(error(range, "expected both range bounds"));
                };
                let start = integer(start)?;
                let mut end = integer(end)?;
                if matches!(range.limits, syn::RangeLimits::Closed(_)) {
                    end = end
                        .checked_add(1)
                        .ok_or_else(|| error(range, "loop bound overflow"))?;
                }
                if end.saturating_sub(start) > 256 {
                    return Err(error(range, "loop expansion is limited to 256 iterations"));
                }
                for _ in start..end {
                    self.block(&loop_.body, env)?;
                }
                Ok(())
            }
            _ => Err(error(
                stmt,
                "supported statements: let, assignment, if/else, blocks, and bounded for _ loops",
            )),
        }
    }
}
fn generic_integers(arguments: &PathArguments) -> syn::Result<Vec<u64>> {
    let PathArguments::AngleBracketed(args) = arguments else {
        return Err(error(arguments, "expected literal const arguments"));
    };
    args.args
        .iter()
        .map(|arg| {
            if let GenericArgument::Const(expr) = arg {
                integer(expr)
            } else {
                Err(error(arg, "expected literal const argument"))
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_incomplete_and_unsupported_logic() {
        for (source, message) in [
            (
                "fn f(a:&bool,o:&mut bool) {if *a {*o=true;}}",
                "not assigned on every path",
            ),
            ("fn f(o:&mut bool) {*o=!*o;}", "read before assignment"),
            ("fn f(a:&bool,o:&mut bool) {*a=true;*o=false;}", "mutable"),
            ("fn f(a:&Bits<4>,o:&mut Bits<8>) {*o=*a;}", "width mismatch"),
            (
                "fn f(a:&Bits<4>,o:&mut bool) {*o=a.bit(4);}",
                "slice out of bounds",
            ),
            (
                "fn f(o:&mut bool) {loop {*o=true;}}",
                "supported statements",
            ),
            (
                "fn f(o:&mut bool) {*o=true;for _ in 0..257 {*o=!*o;}}",
                "256 iterations",
            ),
            (
                "fn f(o:&mut bool) {let mut x=true;{let x=false;}*o=x;}",
                "shadowing",
            ),
        ] {
            let err = expand(syn::parse_str(source).unwrap()).unwrap_err();
            assert!(err.to_string().contains(message), "{err}");
        }
    }
}
