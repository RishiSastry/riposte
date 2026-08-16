//! Compiler pipeline as a library so both the CLI and integration/snapshot tests share one
//! entry point. Pipeline (SPEC §5): lex → parse (recovery) → name/scope+structure → emit.

use riposte_diagnostics::{render_report, Severity, SourceFile};
use serde_json::Value;

pub struct Compiled {
    /// The `diag.json` report (always produced).
    pub report: Value,
    /// The `policy.json` IR — `Some` only when there are no error-severity diagnostics.
    pub policy: Option<Value>,
    pub has_error: bool,
}

/// Run the full front end on one source file. `name` is used only for diagnostic spans.
pub fn compile(name: &str, src: &str) -> Compiled {
    let (toks, mut diags) = riposte_lexer::lex(src);
    let parsed = riposte_parser::parse(src, &toks);
    diags.extend(parsed.diags);
    if let Some(prog) = &parsed.program {
        diags.extend(riposte_typeck::check(prog));
    }

    let has_error = diags.iter().any(|d| d.code.severity == Severity::Error);
    let sf = SourceFile::new(name.to_string(), src.to_string());
    let report = render_report(&sf, &diags);

    let policy = match (&parsed.program, has_error) {
        (Some(prog), false) => Some(riposte_emit::emit_policy(prog, src)),
        _ => None,
    };

    Compiled { report, policy, has_error }
}
