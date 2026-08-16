//! Type lattice + predicate-signature loading from the shared `predicates.toml`.
//!
//! The signatures are read from the SAME file the Python runtime loads, so the compiler that
//! type-checks a call and the interpreter that executes it can never disagree (SPEC §4.4).

use std::collections::HashMap;
use std::sync::OnceLock;

use serde::Deserialize;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Base {
    Num,
    Frac,
    Bool,
    Tribool,
    Type,
    Status,
    Mon,
    Move,
    Eff,
    Str,
    Side,
    Hazard,
    Screen,
    Unknown,
}

/// A value type: a base plus whether it is an estimate (`est`). `est` is meaningful mainly
/// for numeric bases; comparisons involving an est operand yield `Tribool` (SPEC §4.2).
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Ty {
    pub base: Base,
    pub est: bool,
}

impl Ty {
    pub const fn fact(base: Base) -> Ty {
        Ty { base, est: false }
    }
    pub const fn est(base: Base) -> Ty {
        Ty { base, est: true }
    }
    pub fn is_numeric(self) -> bool {
        matches!(self.base, Base::Num | Base::Frac)
    }
    pub fn display(self) -> String {
        let b = match self.base {
            Base::Num => "num",
            Base::Frac => "frac",
            Base::Bool => "bool",
            Base::Tribool => "tribool",
            Base::Type => "type",
            Base::Status => "status",
            Base::Mon => "mon",
            Base::Move => "move",
            Base::Eff => "eff",
            Base::Str => "str",
            Base::Side => "side",
            Base::Hazard => "hazard",
            Base::Screen => "screen",
            Base::Unknown => "?",
        };
        if self.est {
            format!("est {b}")
        } else {
            b.to_string()
        }
    }
}

pub const EFF_CATEGORIES: &[&str] = &[
    "immune",
    "strongly_resisted",
    "resisted",
    "neutral",
    "super",
    "overwhelming",
];

/// A predicate signature as the type checker needs it. `infix`/`doc` from predicates.toml
/// are consumed on the Python/MCP side (predicate_reference), not here, so they are dropped.
#[derive(Clone, Debug)]
pub struct Sig {
    pub params: Vec<Ty>,
    pub ret: Ty,
}

#[derive(Deserialize)]
struct RawFile {
    predicates: HashMap<String, RawEntry>,
}

#[derive(Deserialize)]
struct RawEntry {
    params: Vec<String>,
    ret: String,
    // `infix` and `doc` also exist in predicates.toml but are only used Python-side; serde
    // ignores the unknown keys here.
}

fn parse_base(tok: &str) -> Base {
    match tok {
        "num" => Base::Num,
        "frac" => Base::Frac,
        "bool" => Base::Bool,
        "tribool" => Base::Tribool,
        "type" => Base::Type,
        "status" => Base::Status,
        "mon" => Base::Mon,
        "move" => Base::Move,
        "eff" => Base::Eff,
        "str" => Base::Str,
        "side" => Base::Side,
        "hazard" => Base::Hazard,
        "screen" => Base::Screen,
        _ => Base::Unknown,
    }
}

/// Parse a type string like `"est frac"`, `"tribool"`, `"eff"`.
fn parse_ty(s: &str) -> Ty {
    let mut it = s.split_whitespace();
    match it.next() {
        Some("est") => Ty::est(parse_base(it.next().unwrap_or(""))),
        Some(base) => Ty::fact(parse_base(base)),
        None => Ty::fact(Base::Unknown),
    }
}

const PREDICATES_TOML: &str = include_str!("../../../../predicates.toml");

/// Predicate signatures, parsed once from the embedded `predicates.toml`.
pub fn signatures() -> &'static HashMap<String, Sig> {
    static SIGS: OnceLock<HashMap<String, Sig>> = OnceLock::new();
    SIGS.get_or_init(|| {
        let raw: RawFile = toml::from_str(PREDICATES_TOML).expect("predicates.toml parses");
        raw.predicates
            .into_iter()
            .map(|(name, e)| {
                let sig = Sig {
                    params: e.params.iter().map(|p| parse_ty(p)).collect(),
                    ret: parse_ty(&e.ret),
                };
                (name, sig)
            })
            .collect()
    })
}
