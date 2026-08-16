//! Abstract syntax tree for Riposte (SPEC §4.1, §4.7). Every node carries a [`Span`] so
//! diagnostics can point precisely. Kept free of type information — the compile-time kinds
//! (fact/est/tribool) are computed by `typeck` over this tree, not stored in it.

use riposte_diagnostics::Span;

/// An interned-ish string slice lifted to an owned value with its source span.
#[derive(Debug, Clone, PartialEq)]
pub struct Ident {
    pub text: String,
    pub span: Span,
}

#[derive(Debug, Clone)]
pub struct Program {
    pub bot_name: Ident, // from the string literal, quotes stripped
    pub format: Ident,
    pub on_turn: Option<Block>,
    pub on_forced_switch: Option<Block>,
    pub span: Span,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Event {
    Turn,
    ForcedSwitch,
}

#[derive(Debug, Clone)]
pub struct Block {
    pub event: Event,
    pub rules: Vec<Rule>,
    pub span: Span,
}

/// A rule. `name`/`when` are both `None` exactly for the mandatory `otherwise` rule.
#[derive(Debug, Clone)]
pub struct Rule {
    pub name: Option<Ident>,
    pub when: Option<Expr>,
    pub action: Action,
    pub span: Span,
}

// ─────────────────────────────── expressions ───────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CmpOp {
    Eq,
    Ne,
    Lt,
    Le,
    Gt,
    Ge,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResolveOp {
    Likely,
    WorstCase,
    BestCase,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EffOp {
    AtLeast,
    AtMost,
}

/// One segment of a dotted path; `call` is `Some` for a predicate/accessor call like
/// `has_hazard(stealth_rock)` or a free call like `matchup_score(it, opponent.active)`.
#[derive(Debug, Clone)]
pub struct Seg {
    pub name: Ident,
    pub call: Option<Vec<Expr>>,
    pub span: Span,
}

/// A dotted path: `my.active`, `opponent.active.primary_type`,
/// `opponent.side.has_hazard(stealth_rock)`, or a bare call `can_ko(a, b)`.
#[derive(Debug, Clone)]
pub struct Path {
    pub segs: Vec<Seg>,
    pub span: Span,
}

#[derive(Debug, Clone)]
pub enum Expr {
    Path(Path),
    Str(Ident),                          // string literal, quotes stripped
    Num { raw: String, is_float: bool, span: Span },
    Resolve { op: ResolveOp, arg: Box<Expr>, span: Span },
    Outspeeds { left: Box<Expr>, right: Box<Expr>, span: Span },
    Knows { mon: Box<Expr>, move_lit: Box<Expr>, span: Span },
    Not { arg: Box<Expr>, span: Span },
    And { operands: Vec<Expr>, span: Span },
    Or { operands: Vec<Expr>, span: Span },
    Compare { op: CmpOp, left: Box<Expr>, right: Box<Expr>, span: Span },
    EffCompare { op: EffOp, left: Box<Expr>, cat: Ident, span: Span },
    Exists { domain: Ident, var: Ident, body: Box<Expr>, span: Span },
}

impl Expr {
    pub fn span(&self) -> Span {
        match self {
            Expr::Path(p) => p.span,
            Expr::Str(i) => i.span,
            Expr::Num { span, .. }
            | Expr::Resolve { span, .. }
            | Expr::Outspeeds { span, .. }
            | Expr::Knows { span, .. }
            | Expr::Not { span, .. }
            | Expr::And { span, .. }
            | Expr::Or { span, .. }
            | Expr::Compare { span, .. }
            | Expr::EffCompare { span, .. }
            | Expr::Exists { span, .. } => *span,
        }
    }
}

// ──────────────────────────────── actions ─────────────────────────────────

#[derive(Debug, Clone)]
pub enum Action {
    /// `use "move_id" [with tera]`
    UseMove { move_id: Ident, tera: bool, span: Span },
    /// `use strongest_move against <target> [with tera]`
    UseStrongest { target: Path, tera: bool, span: Span },
    /// `switch_to best <domain> by <key>`
    Switch { domain: Ident, key: Expr, span: Span },
}

impl Action {
    pub fn span(&self) -> Span {
        match self {
            Action::UseMove { span, .. }
            | Action::UseStrongest { span, .. }
            | Action::Switch { span, .. } => *span,
        }
    }
}
