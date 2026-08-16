//! IR emitter: lower the AST to the `policy.json` IR (mirrors `runtime/riposte_rt/ir.py`).
//!
//! Lowering choices (refined in M2 when the type system exists):
//! - A single-segment call `p(args)` → `Pred{name:p, args}` (free predicate: `can_ko`,
//!   `matchup_score`, `resists`, `hp_fraction`, `effectiveness`).
//! - A multi-segment path ending in a call, e.g. `opponent.side.has_hazard(x)`, →
//!   `Pred{name:has_hazard, args:[Ref(["opponent","side"]), x]}` (receiver as first arg).
//! - A multi-segment path with no call → `Ref(path)` (`opponent.active.primary_type`).
//! - A bare identifier that is neither a namespace nor the binder is an enum atom →
//!   `Lit{str}` (`stealth_rock`, effectiveness categories).
//! - Inside `exists <dom> <b> where …`, references to the binder `b` lower to `Ref(["it"])`,
//!   matching the runtime's `it` binding.

use riposte_ast::*;
use serde_json::{json, Value};

const NAMESPACES: &[&str] = &["my", "opponent", "field"];

pub fn emit_policy(prog: &Program, source: &str) -> Value {
    json!({
        "ir_version": "0.1",
        "header": {
            "name": prog.bot_name.text,
            "format": prog.format.text,
            "source_hash": fnv1a_hex(source),
            "compiler_version": env!("CARGO_PKG_VERSION"),
        },
        "on_turn": prog.on_turn.as_ref().map(emit_block).unwrap_or_else(|| json!([])),
        "on_forced_switch": prog.on_forced_switch.as_ref().map(emit_block).unwrap_or_else(|| json!([])),
    })
}

fn emit_block(block: &Block) -> Value {
    Value::Array(block.rules.iter().map(emit_rule).collect())
}

fn emit_rule(rule: &Rule) -> Value {
    json!({
        "rule_name": rule.name.as_ref().map(|n| n.text.clone()).unwrap_or_else(|| "otherwise".into()),
        "when": rule.when.as_ref().map(|e| emit_expr(e, None)).unwrap_or(Value::Null),
        "action": emit_action(&rule.action),
    })
}

fn emit_action(action: &Action) -> Value {
    match action {
        Action::UseMove { move_id, tera, .. } => json!({
            "kind": "use_move", "move_id": move_id.text, "tera": tera,
        }),
        Action::UseStrongest { target, tera, .. } => json!({
            "kind": "use_strongest", "target": emit_path(target, None), "tera": tera,
        }),
        Action::Switch { domain, key, .. } => json!({
            "kind": "switch_best", "domain": domain.text, "order": "max",
            "by": emit_expr(key, None),
        }),
    }
}

/// `binder` is the current `exists` binder name (if any); references to it lower to `it`.
fn emit_expr(e: &Expr, binder: Option<&str>) -> Value {
    match e {
        Expr::Str(s) => json!({"kind": "lit", "type": "str", "value": s.text}),
        Expr::Num { raw, is_float, .. } => {
            let value = if *is_float {
                json!(raw.parse::<f64>().unwrap_or(0.0))
            } else {
                json!(raw.parse::<i64>().unwrap_or(0))
            };
            json!({"kind": "lit", "type": if *is_float { "frac" } else { "num" }, "value": value})
        }
        Expr::Path(p) => emit_path(p, binder),
        Expr::Resolve { op, arg, .. } => json!({
            "kind": "resolve", "op": resolve_op(*op), "arg": emit_expr(arg, binder),
        }),
        Expr::Outspeeds { left, right, .. } => json!({
            "kind": "outspeeds", "left": emit_expr(left, binder), "right": emit_expr(right, binder),
        }),
        Expr::Knows { mon, move_lit, .. } => json!({
            "kind": "pred", "name": "knows",
            "args": [emit_expr(mon, binder), emit_expr(move_lit, binder)],
        }),
        Expr::Not { arg, .. } => json!({"kind": "not", "operand": emit_expr(arg, binder)}),
        Expr::And { operands, .. } => json!({
            "kind": "and", "operands": operands.iter().map(|o| emit_expr(o, binder)).collect::<Vec<_>>(),
        }),
        Expr::Or { operands, .. } => json!({
            "kind": "or", "operands": operands.iter().map(|o| emit_expr(o, binder)).collect::<Vec<_>>(),
        }),
        Expr::Compare { op, left, right, .. } => json!({
            "kind": "compare", "op": cmp_op(*op),
            "left": emit_expr(left, binder), "right": emit_expr(right, binder),
        }),
        Expr::EffCompare { op, left, cat, .. } => json!({
            "kind": "eff_cmp", "op": eff_op(*op),
            "left": emit_expr(left, binder), "right": cat.text,
        }),
        Expr::Exists { domain, var, body, .. } => json!({
            "kind": "exists", "domain": domain.text, "var": var.text,
            "body": emit_expr(body, Some(&var.text)),
        }),
    }
}

fn emit_path(p: &Path, binder: Option<&str>) -> Value {
    let n = p.segs.len();
    let last = &p.segs[n - 1];

    // free predicate call: single segment with args
    if n == 1 {
        if let Some(args) = &last.call {
            return json!({
                "kind": "pred", "name": last.name.text,
                "args": args.iter().map(|a| emit_expr(a, binder)).collect::<Vec<_>>(),
            });
        }
        // bare identifier
        let name = &last.name.text;
        if name == "it" || Some(name.as_str()) == binder {
            return json!({"kind": "ref", "path": ["it"]});
        }
        if NAMESPACES.contains(&name.as_str()) {
            return json!({"kind": "ref", "path": [name]});
        }
        // enum atom (e.g. stealth_rock, super)
        return json!({"kind": "lit", "type": "str", "value": name});
    }

    // multi-segment: receiver = all but last
    let receiver = ref_path(&p.segs[..n - 1], binder);
    if let Some(args) = &last.call {
        // method-style predicate: receiver becomes the first argument
        let mut arg_vals = vec![receiver];
        arg_vals.extend(args.iter().map(|a| emit_expr(a, binder)));
        return json!({"kind": "pred", "name": last.name.text, "args": arg_vals});
    }
    // pure field access path
    ref_path(&p.segs, binder)
}

/// Build a `Ref` from bare segment names, normalizing the binder / `it` root.
fn ref_path(segs: &[Seg], binder: Option<&str>) -> Value {
    let mut names: Vec<String> = Vec::with_capacity(segs.len());
    for (i, s) in segs.iter().enumerate() {
        let t = &s.name.text;
        if i == 0 && (t == "it" || Some(t.as_str()) == binder) {
            names.push("it".to_string());
        } else {
            names.push(t.clone());
        }
    }
    json!({"kind": "ref", "path": names})
}

fn resolve_op(op: ResolveOp) -> &'static str {
    match op {
        ResolveOp::Likely => "likely",
        ResolveOp::WorstCase => "worst_case",
        ResolveOp::BestCase => "best_case",
    }
}

fn cmp_op(op: CmpOp) -> &'static str {
    match op {
        CmpOp::Eq => "=",
        CmpOp::Ne => "!=",
        CmpOp::Lt => "<",
        CmpOp::Le => "<=",
        CmpOp::Gt => ">",
        CmpOp::Ge => ">=",
    }
}

fn eff_op(op: EffOp) -> &'static str {
    match op {
        EffOp::AtLeast => "at_least",
        EffOp::AtMost => "at_most",
    }
}

/// FNV-1a 64-bit content hash → hex. Stable across runs/platforms (unlike DefaultHasher).
fn fnv1a_hex(s: &str) -> String {
    let mut h: u64 = 0xcbf29ce484222325;
    for b in s.bytes() {
        h ^= b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    format!("{h:016x}")
}
