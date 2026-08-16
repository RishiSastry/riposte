//! Static checks (SPEC §5 name/scope + §4.2 type system).
//!
//! M2 implements the epistemic type system on top of M1's structure/name checks:
//! - fact vs est propagation; comparisons with an est operand yield `tribool`.
//! - `when` (and every boolean position) requires `bool`; a `tribool` there is **E030**.
//! - resolvers `likely`/`worst_case`/`best_case` take `tribool`→`bool`; on a fact → **E031**.
//! - effectiveness is categorical: numeric comparison → **E032**; use `at_least`/`at_most`.
//! - predicate calls are checked against `predicates.toml` (**E022** unknown, **E034** arity, **E033** argument type).
//!
//! Structure checks from M1 remain: **E040** missing `otherwise`, **E041** illegal action.

mod sig;

use riposte_ast::*;
use riposte_diagnostics::{
    Diagnostic, Span, E020, E021, E022, E023, E030, E031, E032, E033, E034, E040, E041,
};
use sig::{signatures, Base, Ty, EFF_CATEGORIES};

pub fn check(prog: &Program) -> Vec<Diagnostic> {
    let mut c = Checker { diags: Vec::new() };
    if let Some(b) = &prog.on_turn {
        c.block(b);
    }
    if let Some(b) = &prog.on_forced_switch {
        c.block(b);
    }
    c.diags
}

/// Lexical scope for `it` and `exists` binders. Binders range over `bench` (our side), so a
/// bound mon's stats are facts.
#[derive(Clone, Default)]
struct Ctx {
    it_bound: bool,
    binders: Vec<String>,
}

struct Checker {
    diags: Vec<Diagnostic>,
}

impl Checker {
    fn emit(&mut self, d: Diagnostic) {
        self.diags.push(d);
    }

    fn block(&mut self, block: &Block) {
        // E040: non-empty and ends with `otherwise`.
        match block.rules.last() {
            Some(last) if last.name.is_none() => {}
            _ => self.emit(Diagnostic::new(E040, Span::new(block.span.end, block.span.end))),
        }
        for r in block.rules.iter().take(block.rules.len().saturating_sub(1)) {
            if r.name.is_none() {
                self.emit(
                    Diagnostic::new(E040, r.span)
                        .with_message("`otherwise` must be the last rule in the block"),
                );
            }
        }

        for rule in &block.rules {
            if block.event == Event::ForcedSwitch && !matches!(rule.action, Action::Switch { .. }) {
                self.emit(Diagnostic::new(E041, rule.action.span()));
            }
            if let Some(when) = &rule.when {
                self.expect_bool(when, &Ctx::default());
            }
            self.action(&rule.action);
        }
    }

    fn action(&mut self, action: &Action) {
        match action {
            Action::UseStrongest { target, .. } => {
                self.resolve_ref(target, &Ctx::default());
            }
            Action::Switch { key, .. } => {
                // `best … by <key>` binds `it`; the key is a sort value (num/frac), not a bool.
                let ctx = Ctx { it_bound: true, ..Default::default() };
                self.infer(key, &ctx);
            }
            Action::UseMove { .. } => {}
        }
    }

    // ── boolean positions ──
    fn expect_bool(&mut self, e: &Expr, ctx: &Ctx) {
        let t = self.infer(e, ctx);
        match t.base {
            Base::Bool | Base::Unknown => {}
            Base::Tribool => self.emit(Diagnostic::new(E030, e.span())),
            _ => self.emit(
                Diagnostic::new(E033, e.span())
                    .with_message(format!("expected bool, found {}", t.display())),
            ),
        }
    }

    // ── inference ──
    fn infer(&mut self, e: &Expr, ctx: &Ctx) -> Ty {
        match e {
            Expr::Str(_) => Ty::fact(Base::Str),
            Expr::Num { is_float, .. } => Ty::fact(if *is_float { Base::Frac } else { Base::Num }),
            Expr::Path(p) => self.infer_path(p, ctx),
            Expr::Resolve { op: _, arg, span } => {
                let t = self.infer(arg, ctx);
                match t.base {
                    Base::Tribool => {}
                    Base::Bool => self.emit(Diagnostic::new(E031, *span)),
                    Base::Unknown => {}
                    _ => self.emit(
                        Diagnostic::new(E033, arg.span())
                            .with_message(format!("resolver expects tribool, found {}", t.display())),
                    ),
                }
                Ty::fact(Base::Bool)
            }
            Expr::Outspeeds { left, right, span } => {
                self.call("outspeeds", *span, &[left, right], ctx)
            }
            Expr::Knows { mon, move_lit, span } => self.call("knows", *span, &[mon, move_lit], ctx),
            Expr::Not { arg, .. } => {
                self.expect_bool(arg, ctx);
                Ty::fact(Base::Bool)
            }
            Expr::And { operands, .. } | Expr::Or { operands, .. } => {
                for o in operands {
                    self.expect_bool(o, ctx);
                }
                Ty::fact(Base::Bool)
            }
            Expr::Compare { op, left, right, .. } => self.infer_compare(*op, left, right, ctx),
            Expr::EffCompare { left, cat, span, .. } => {
                let t = self.infer(left, ctx);
                if t.base != Base::Eff && t.base != Base::Unknown {
                    self.emit(Diagnostic::new(E032, left.span()).with_message(format!(
                        "at_least/at_most needs an effectiveness value, found {}",
                        t.display()
                    )));
                }
                if !EFF_CATEGORIES.contains(&cat.text.as_str()) {
                    self.emit(Diagnostic::new(E032, *span).with_message(format!(
                        "unknown effectiveness category `{}` (expected one of: {})",
                        cat.text,
                        EFF_CATEGORIES.join(", ")
                    )));
                }
                Ty::fact(Base::Bool)
            }
            Expr::Exists { var, body, .. } => {
                let mut inner = ctx.clone();
                inner.binders.push(var.text.clone());
                self.expect_bool(body, &inner);
                Ty::fact(Base::Bool)
            }
        }
    }

    fn infer_compare(&mut self, op: CmpOp, left: &Expr, right: &Expr, ctx: &Ctx) -> Ty {
        let tl = self.infer(left, ctx);
        let tr = self.infer(right, ctx);
        // Q2: effectiveness must not be compared numerically.
        if tl.base == Base::Eff || tr.base == Base::Eff {
            let span = if tl.base == Base::Eff { left.span() } else { right.span() };
            self.emit(Diagnostic::new(E032, span));
            return Ty::fact(Base::Bool);
        }
        if tl.base == Base::Unknown || tr.base == Base::Unknown {
            return Ty::fact(Base::Bool);
        }
        if tl.is_numeric() && tr.is_numeric() {
            // est propagates to tribool (SPEC §4.2 rule 1).
            let est = tl.est || tr.est;
            return Ty { base: if est { Base::Tribool } else { Base::Bool }, est: false };
        }
        // non-numeric: only equality between the same base is allowed.
        let ordering = matches!(op, CmpOp::Lt | CmpOp::Le | CmpOp::Gt | CmpOp::Ge);
        if ordering || tl.base != tr.base {
            self.emit(Diagnostic::new(E033, left.span().to(right.span())).with_message(format!(
                "cannot compare {} with {}",
                tl.display(),
                tr.display()
            )));
        }
        let est = tl.est || tr.est;
        Ty { base: if est { Base::Tribool } else { Base::Bool }, est: false }
    }

    /// A predicate call by name with already-collected argument expressions (infix forms).
    fn call(&mut self, name: &str, name_span: Span, args: &[&Expr], ctx: &Ctx) -> Ty {
        let arg_tys: Vec<(Ty, Span)> = args.iter().map(|a| (self.infer(a, ctx), a.span())).collect();
        match signatures().get(name) {
            None => Ty::fact(Base::Unknown), // for future infix additions
            Some(sig) => {
                self.apply_sig(name, name_span, sig, &arg_tys);
                sig.ret
            }
        }
    }

    /// Check arity + argument compatibility against a signature.
    fn apply_sig(&mut self, name: &str, name_span: Span, sig: &sig::Sig, arg_tys: &[(Ty, Span)]) {
        if arg_tys.len() != sig.params.len() {
            self.emit(Diagnostic::new(E034, name_span).with_message(format!(
                "`{}` takes {} argument(s), got {}",
                name,
                sig.params.len(),
                arg_tys.len()
            )));
            return;
        }
        for (pty, (aty, span)) in sig.params.iter().zip(arg_tys) {
            if !compatible(pty.base, aty.base) {
                self.emit(Diagnostic::new(E033, *span).with_message(format!(
                    "`{}` expects {}, found {}",
                    name,
                    pty.display(),
                    aty.display()
                )));
            }
        }
    }

    fn infer_path(&mut self, p: &Path, ctx: &Ctx) -> Ty {
        let n = p.segs.len();
        let last = &p.segs[n - 1];

        // free predicate call: single segment with args
        if n == 1 {
            if let Some(args) = &last.call {
                return self.check_pred_call(&last.name, args, None, ctx);
            }
            // bare identifier
            let name = last.name.text.as_str();
            if name == "it" {
                if !ctx.it_bound {
                    self.emit(Diagnostic::new(E023, last.span));
                }
                return Ty::fact(Base::Mon);
            }
            if ctx.binders.iter().any(|b| b == name) {
                return Ty::fact(Base::Mon);
            }
            if matches!(name, "my" | "opponent" | "field") {
                return Ty::fact(Base::Unknown); // bare namespace — not a value
            }
            // enum atom (stealth_rock, super, a move id, …)
            return Ty::fact(Base::Str);
        }

        // multi-segment ending in a call: method-style predicate, receiver = leading path
        if let Some(args) = &last.call {
            let receiver = Path { segs: p.segs[..n - 1].to_vec(), span: p.span };
            return self.check_pred_call(&last.name, args, Some(&receiver), ctx);
        }

        // pure field access
        self.resolve_ref(p, ctx)
    }

    fn check_pred_call(
        &mut self,
        name: &Ident,
        args: &[Expr],
        receiver: Option<&Path>,
        ctx: &Ctx,
    ) -> Ty {
        let Some(sig) = signatures().get(&name.text) else {
            self.emit(
                Diagnostic::new(E022, name.span)
                    .with_message(format!("unknown predicate `{}`", name.text)),
            );
            // still infer args to surface nested errors
            for a in args {
                self.infer(a, ctx);
            }
            return Ty::fact(Base::Unknown);
        };
        // Build the effective argument type list (receiver first, if any).
        let mut arg_tys: Vec<(Ty, Span)> = Vec::new();
        if let Some(recv) = receiver {
            arg_tys.push((self.resolve_ref(recv, ctx), recv.span));
        }
        for a in args {
            arg_tys.push((self.infer(a, ctx), a.span()));
        }
        self.apply_sig(&name.text, name.span, sig, &arg_tys);
        sig.ret
    }

    /// Type a pure field-access path against the state surface (SPEC §4.3), emitting E020 for
    /// unrevealed info and E023 for an unbound `it`.
    fn resolve_ref(&mut self, p: &Path, ctx: &Ctx) -> Ty {
        // E020: opponent.(active|bench)…moves is unrevealed. Return early so we don't also
        // report it as an unknown field (E021).
        if p.segs.len() >= 3
            && p.segs[0].name.text == "opponent"
            && matches!(p.segs[1].name.text.as_str(), "active" | "bench")
            && p.segs.iter().any(|s| s.name.text == "moves")
        {
            self.emit(Diagnostic::new(E020, p.span));
            return Ty::fact(Base::Unknown);
        }

        let names: Vec<&str> = p.segs.iter().map(|s| s.name.text.as_str()).collect();
        let root = names[0];

        if root == "it" {
            if !ctx.it_bound {
                self.emit(Diagnostic::new(E023, p.segs[0].span));
            }
            return mon_field_ty(false, &names[1..]).unwrap_or_else(|| self.unknown_field(p));
        }
        if ctx.binders.iter().any(|b| b == root) {
            return mon_field_ty(false, &names[1..]).unwrap_or_else(|| self.unknown_field(p));
        }

        let is_opp = root == "opponent";
        match root {
            "my" | "opponent" => match names.get(1).copied() {
                Some("active") => {
                    mon_field_ty(is_opp, &names[2..]).unwrap_or_else(|| self.unknown_field(p))
                }
                Some("side") => side_field_ty(&names[2..]).unwrap_or_else(|| self.unknown_field(p)),
                _ => self.unknown_field(p),
            },
            "field" => field_ns_ty(&names[1..]).unwrap_or_else(|| self.unknown_field(p)),
            _ => self.unknown_field(p),
        }
    }

    fn unknown_field(&mut self, p: &Path) -> Ty {
        self.emit(
            Diagnostic::new(E021, p.span)
                .with_message(format!("unknown state field: {}", path_str(p))),
        );
        Ty::fact(Base::Unknown)
    }
}

// ── state-surface field typing (SPEC §4.3) ──

fn mon_field_ty(is_opp: bool, fields: &[&str]) -> Option<Ty> {
    let est_if_opp = |b: Base| if is_opp { Ty::est(b) } else { Ty::fact(b) };
    Some(match fields {
        [] => Ty::fact(Base::Mon),
        ["hp_fraction"] => Ty::fact(Base::Frac),
        ["max_hp"] => Ty::fact(Base::Num),
        ["species"] => Ty::fact(Base::Str),
        ["primary_type"] | ["types"] => Ty::fact(Base::Type),
        ["status"] => Ty::fact(Base::Status),
        ["ability"] => est_if_opp(Base::Str),
        ["item"] => est_if_opp(Base::Str),
        ["is_tera_available"] | ["first_turn_out"] => Ty::fact(Base::Bool),
        ["boosts", _] => Ty::fact(Base::Num),
        ["stats", _] => est_if_opp(Base::Num),
        ["revealed_moves"] => Ty::fact(Base::Unknown),
        _ => return None,
    })
}

fn side_field_ty(fields: &[&str]) -> Option<Ty> {
    Some(match fields {
        [] => Ty::fact(Base::Side),
        ["tailwind"] => Ty::fact(Base::Bool),
        _ => return None,
    })
}

fn field_ns_ty(fields: &[&str]) -> Option<Ty> {
    Some(match fields {
        ["weather"] | ["terrain"] => Ty::fact(Base::Str),
        ["trick_room"] => Ty::fact(Base::Bool),
        ["turn"] => Ty::fact(Base::Num),
        _ => return None,
    })
}

/// Whether an argument of base `arg` satisfies a parameter of base `param`.
fn compatible(param: Base, arg: Base) -> bool {
    if arg == Base::Unknown || param == Base::Unknown {
        return true; // recover
    }
    if param == arg {
        return true;
    }
    match param {
        Base::Hazard | Base::Screen | Base::Move => arg == Base::Str, // enum atoms / move ids
        Base::Num | Base::Frac => matches!(arg, Base::Num | Base::Frac),
        _ => false,
    }
}

fn path_str(p: &Path) -> String {
    p.segs.iter().map(|s| s.name.text.clone()).collect::<Vec<_>>().join(".")
}
