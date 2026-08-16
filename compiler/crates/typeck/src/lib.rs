//! Static checks. For M1 this is **name/scope + structure only** (SPEC M1: "name checking
//! only, types stubbed"). The epistemic type system (fact/est/tribool propagation, E030/
//! E031/E032) lands in M2 and will extend this crate.
//!
//! M1 checks:
//! - E040 every block must end with `otherwise` (policy totality).
//! - E041 `on forced_switch` allows switch actions only.
//! - E020 unrevealed information (`opponent.active.moves` — use `revealed_moves`).
//! - E023 `it` used outside a `best … by` binding.
//! - E022 unknown predicate name.

use riposte_ast::*;
use riposte_diagnostics::{Diagnostic, Span, E020, E022, E023, E040, E041};

/// Predicates + accessor-functions known to v1 (SPEC §4.4). Infix `outspeeds`/`knows` are
/// syntactic, but `knows` is also accepted in call form.
const KNOWN_PREDICATES: &[&str] = &[
    "damage_frac",
    "can_ko",
    "guaranteed_ko",
    "effectiveness",
    "resists",
    "is_immune",
    "hazard_damage_on_switch",
    "matchup_score",
    "revealed",
    "knows",
    "has_hazard",
    "hazard_layers",
    "has_screen",
    "hp_fraction",
];

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

struct Checker {
    diags: Vec<Diagnostic>,
}

impl Checker {
    fn block(&mut self, block: &Block) {
        // E040: block must be non-empty and end with `otherwise`.
        match block.rules.last() {
            Some(last) if last.name.is_none() => {}
            _ => {
                let at = Span::new(block.span.end, block.span.end);
                self.diags.push(Diagnostic::new(E040, at));
            }
        }
        // Any earlier `otherwise` (not last) is also flagged, since rules after it are dead
        // and the block is malformed.
        for r in block.rules.iter().take(block.rules.len().saturating_sub(1)) {
            if r.name.is_none() {
                self.diags.push(
                    Diagnostic::new(E040, r.span)
                        .with_message("`otherwise` must be the last rule in the block"),
                );
            }
        }

        for rule in &block.rules {
            if block.event == Event::ForcedSwitch && !is_switch(&rule.action) {
                self.diags.push(Diagnostic::new(E041, rule.action.span()));
            }
            if let Some(when) = &rule.when {
                self.expr(when, false);
            }
            self.action(&rule.action);
        }
    }

    fn action(&mut self, action: &Action) {
        match action {
            Action::UseStrongest { target, .. } => self.path(target, false),
            Action::Switch { key, .. } => self.expr(key, true), // `best … by` binds `it`
            Action::UseMove { .. } => {}
        }
    }

    fn expr(&mut self, e: &Expr, it_bound: bool) {
        match e {
            Expr::Path(p) => self.path(p, it_bound),
            Expr::Str(_) | Expr::Num { .. } => {}
            Expr::Resolve { arg, .. } | Expr::Not { arg, .. } => self.expr(arg, it_bound),
            Expr::Outspeeds { left, right, .. } | Expr::Knows { mon: left, move_lit: right, .. } => {
                self.expr(left, it_bound);
                self.expr(right, it_bound);
            }
            Expr::And { operands, .. } | Expr::Or { operands, .. } => {
                for o in operands {
                    self.expr(o, it_bound);
                }
            }
            Expr::Compare { left, right, .. } => {
                self.expr(left, it_bound);
                self.expr(right, it_bound);
            }
            Expr::EffCompare { left, .. } => self.expr(left, it_bound),
            // exists binds a *named* var (not `it`); `it` boundness is unchanged inside.
            Expr::Exists { body, .. } => self.expr(body, it_bound),
        }
    }

    fn path(&mut self, p: &Path, it_bound: bool) {
        // E020: opponent.(active|bench)…moves is unrevealed information.
        if p.segs.len() >= 3
            && p.segs[0].name.text == "opponent"
            && matches!(p.segs[1].name.text.as_str(), "active" | "bench")
            && p.segs.iter().any(|s| s.name.text == "moves")
        {
            self.diags.push(Diagnostic::new(E020, p.span));
        }

        // E023: `it` root outside a `best … by` binding.
        if p.segs[0].name.text == "it" && !it_bound {
            self.diags.push(Diagnostic::new(E023, p.segs[0].span));
        }

        // E022: unknown predicate on any called segment.
        for (i, seg) in p.segs.iter().enumerate() {
            if let Some(args) = &seg.call {
                let is_call_head = i == 0 || i == p.segs.len() - 1;
                if is_call_head && !KNOWN_PREDICATES.contains(&seg.name.text.as_str()) {
                    self.diags.push(
                        Diagnostic::new(E022, seg.name.span)
                            .with_message(format!("unknown predicate `{}`", seg.name.text)),
                    );
                }
                for a in args {
                    self.expr(a, it_bound);
                }
            }
        }
    }
}

fn is_switch(action: &Action) -> bool {
    matches!(action, Action::Switch { .. })
}
