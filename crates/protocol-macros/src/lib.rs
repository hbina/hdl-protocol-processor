//! Rust syntax frontend for staged protocol-to-instruction compilation.
use proc_macro::TokenStream;
use quote::quote;
use syn::{Expr, FnArg, ItemFn, Pat, ReturnType, fold::Fold, visit::Visit};

#[proc_macro_attribute]
pub fn protocol(attribute: TokenStream, item: TokenStream) -> TokenStream {
    if !attribute.is_empty() {
        return syn::Error::new(
            proc_macro2::Span::call_site(),
            "#[protocol] takes no arguments",
        )
        .into_compile_error()
        .into();
    }
    match syn::parse::<ItemFn>(item).and_then(expand) {
        Ok(expansion) => expansion.into(),
        Err(error) => error.into_compile_error().into(),
    }
}

fn expand(function: ItemFn) -> syn::Result<proc_macro2::TokenStream> {
    let signature = &function.sig;
    if signature.asyncness.is_some()
        || signature.constness.is_some()
        || signature.unsafety.is_some()
        || signature.abi.is_some()
        || signature.variadic.is_some()
        || !signature.generics.params.is_empty()
        || signature.generics.where_clause.is_some()
        || !matches!(signature.output, ReturnType::Default)
    {
        return Err(syn::Error::new_spanned(
            signature,
            "protocol functions must be ordinary non-generic Rust functions with no return type",
        ));
    }
    let name = &signature.ident;
    if ["drive", "wait"].contains(&name.to_string().as_str()) {
        return Err(syn::Error::new_spanned(
            name,
            "drive and wait are reserved protocol intrinsic names",
        ));
    }
    let visibility = &function.vis;
    let inputs = &signature.inputs;
    let mut wrapper_inputs = inputs.clone();
    for input in &mut wrapper_inputs {
        if let FnArg::Typed(argument) = input
            && let Pat::Ident(binding) = &mut *argument.pat
        {
            binding.mutability = None;
        }
    }
    let mut arguments = Vec::new();
    for input in inputs {
        let FnArg::Typed(argument) = input else {
            return Err(syn::Error::new_spanned(
                input,
                "protocol functions cannot have a receiver",
            ));
        };
        let Pat::Ident(binding) = &*argument.pat else {
            return Err(syn::Error::new_spanned(
                input,
                "use named protocol parameters",
            ));
        };
        if binding.by_ref.is_some() || binding.subpat.is_some() {
            return Err(syn::Error::new_spanned(
                input,
                "use simple parameter bindings",
            ));
        }
        if binding.ident.to_string().starts_with("__protocol_") {
            return Err(syn::Error::new_spanned(
                binding,
                "the __protocol_ prefix is reserved",
            ));
        }
        check_type(&argument.ty)?;
        arguments.push(&binding.ident);
    }
    let mut validator = Validate {
        error: None,
        name: name.to_string(),
    };
    validator.visit_block(&function.block);
    if let Some(error) = validator.error {
        return Err(error);
    }
    let body = Lower.fold_block(*function.block.clone());
    let source = quote!(#function).to_string();
    Ok(quote! {
        #function

        #[allow(non_camel_case_types)]
        #visibility struct #name {}

        impl #name {
            /// Compile this Rust protocol, specializing its input arguments.
            pub fn compile(#wrapper_inputs) -> ::std::result::Result<
                ::protocol_compiler::Program, ::protocol_compiler::CompileError
            > {
                Self::ir(#(#arguments),*)?.lower()
            }

            /// Inspect the captured protocol's specialized effect IR.
            pub fn ir(#wrapper_inputs) -> ::std::result::Result<
                ::protocol_compiler::ProtocolIr, ::protocol_compiler::CompileError
            > {
                let mut __protocol_ir = ::protocol_compiler::ProtocolIr::new(stringify!(#name));
                Self::__emit(&mut __protocol_ir, #(#arguments),*)?;
                Ok(__protocol_ir)
            }

            /// Captured Rust syntax before lowering (formatting is normalized).
            pub fn source() -> &'static str { #source }

            #[doc(hidden)]
            pub fn __emit(
                __protocol_ir: &mut ::protocol_compiler::ProtocolIr, #inputs
            ) -> ::std::result::Result<(), ::protocol_compiler::CompileError> {
                __protocol_ir.enter(stringify!(#name))?;
                #body
                __protocol_ir.leave();
                Ok(())
            }
        }
    })
}

fn check_type(ty: &syn::Type) -> syn::Result<()> {
    let allowed = match ty {
        syn::Type::Path(path) if path.qself.is_none() => {
            let names = [
                "bool",
                "u8",
                "u16",
                "u32",
                "u64",
                "usize",
                "Pin",
                "NonZeroU16",
            ];
            path.path
                .get_ident()
                .is_some_and(|id| names.contains(&id.to_string().as_str()))
        }
        syn::Type::Reference(reference) if reference.mutability.is_none() => {
            matches!(&*reference.elem, syn::Type::Slice(slice)
                if matches!(&*slice.elem, syn::Type::Path(path) if path.path.is_ident("u8")))
        }
        _ => false,
    };
    if allowed {
        Ok(())
    } else {
        Err(syn::Error::new_spanned(
            ty,
            "supported protocol parameters: bool, unsigned integers, Pin, NonZeroU16, and &[u8]",
        ))
    }
}

struct Validate {
    error: Option<syn::Error>,
    name: String,
}

impl Validate {
    fn reject(&mut self, node: impl quote::ToTokens, message: &str) {
        let error = syn::Error::new_spanned(node, message);
        if let Some(first) = &mut self.error {
            first.combine(error);
        } else {
            self.error = Some(error);
        }
    }
}

impl<'ast> Visit<'ast> for Validate {
    fn visit_macro(&mut self, invocation: &'ast syn::Macro) {
        self.reject(invocation, "macros are not supported inside #[protocol]");
    }

    fn visit_pat_ident(&mut self, pattern: &'ast syn::PatIdent) {
        if pattern.ident.to_string().starts_with("__protocol_") {
            self.reject(pattern, "the __protocol_ prefix is reserved");
        }
        syn::visit::visit_pat_ident(self, pattern);
    }

    fn visit_expr(&mut self, expr: &'ast Expr) {
        match expr {
            Expr::While(_) | Expr::Loop(_) => {
                self.reject(expr, "protocol loops must use bounded for loops")
            }
            Expr::Return(_) | Expr::Break(_) | Expr::Continue(_) | Expr::Try(_) => self.reject(
                expr,
                "early exits and ? are not supported in protocol functions",
            ),
            Expr::Closure(_)
            | Expr::Async(_)
            | Expr::Await(_)
            | Expr::Unsafe(_)
            | Expr::Macro(_)
            | Expr::Yield(_) => {
                self.reject(expr, "this Rust construct is not supported by #[protocol]")
            }
            _ => syn::visit::visit_expr(self, expr),
        }
    }

    fn visit_expr_call(&mut self, call: &'ast syn::ExprCall) {
        let Expr::Path(path) = &*call.func else {
            self.reject(
                call,
                "protocol calls must name drive, wait, or another #[protocol] function",
            );
            return;
        };
        let Some(name) = path.path.get_ident() else {
            self.reject(call, "use an unqualified #[protocol] helper name");
            return;
        };
        if name == &self.name {
            self.reject(call, "direct protocol recursion is not supported");
        }
        if (name == "drive" && call.args.len() != 2) || (name == "wait" && call.args.len() != 1) {
            self.reject(call, "drive requires (Pin, bool); wait requires (u16)");
        }
        syn::visit::visit_expr_call(self, call);
    }

    fn visit_expr_method_call(&mut self, call: &'ast syn::ExprMethodCall) {
        if !["get", "len"].contains(&call.method.to_string().as_str()) {
            self.reject(
                call,
                "only get() and len() method calls are supported in protocols",
            );
        }
        syn::visit::visit_expr_method_call(self, call);
    }

    fn visit_item(&mut self, item: &'ast syn::Item) {
        self.reject(
            item,
            "declare annotated protocol helpers outside the protocol body",
        );
    }
}

struct Lower;

impl Fold for Lower {
    fn fold_expr(&mut self, expr: Expr) -> Expr {
        match expr {
            Expr::Call(call) => {
                let Expr::Path(path) = &*call.func else {
                    unreachable!("validated calls")
                };
                let name = path.path.get_ident().unwrap();
                let arguments = call
                    .args
                    .iter()
                    .cloned()
                    .map(|a| self.fold_expr(a))
                    .collect::<Vec<_>>();
                if name == "drive" || name == "wait" {
                    syn::parse_quote! { __protocol_ir.#name(#(#arguments),*)? }
                } else {
                    syn::parse_quote! { #name::__emit(__protocol_ir, #(#arguments),*)? }
                }
            }
            Expr::ForLoop(for_loop) => {
                let mut for_loop = syn::fold::fold_expr_for_loop(self, for_loop);
                for_loop
                    .body
                    .stmts
                    .insert(0, syn::parse_quote! { __protocol_ir.iteration()?; });
                Expr::ForLoop(for_loop)
            }
            _ => syn::fold::fold_expr(self, expr),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_unsupported_syntax_with_specific_diagnostics() {
        for (source, diagnostic) in [
            ("fn p() { while true {} }", "bounded for"),
            ("fn p() { return; }", "early exits"),
            ("fn p() { p(); }", "recursion"),
            ("fn p() { println!(\"hi\"); }", "not supported"),
            ("fn p(x: &mut u8) {}", "supported protocol parameters"),
            ("async fn p() {}", "ordinary non-generic"),
            ("fn p() -> bool { true }", "no return type"),
            ("fn p() { x.push(1); }", "only get() and len()"),
        ] {
            let error = expand(syn::parse_str(source).unwrap()).unwrap_err();
            assert!(error.to_string().contains(diagnostic), "{error}");
        }
    }
}
