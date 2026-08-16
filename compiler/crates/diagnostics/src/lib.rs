//! Diagnostics: spans, error codes, and the `diag.json` output (SPEC §5).
//!
//! Diagnostics are a first-class compiler output. `riposte-c build bot.rpo` always writes
//! `bot.diag.json`; the `docs_tool` field ties each diagnostic to the MCP `explain_error`
//! tool so repair-loop agents can fetch a worked example.

use serde::Serialize;

pub const DIAG_VERSION: &str = "0.1";

/// A byte range into a single source file. Line/col are derived on render via [`SourceFile`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Span {
    pub start: usize,
    pub end: usize,
}

impl Span {
    pub fn new(start: usize, end: usize) -> Self {
        Span { start, end }
    }
    pub fn to(self, other: Span) -> Span {
        Span::new(self.start.min(other.start), self.end.max(other.end))
    }
    pub fn len(self) -> usize {
        self.end.saturating_sub(self.start)
    }
    pub fn is_empty(self) -> bool {
        self.end <= self.start
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Error,
    Warning,
}

/// A stable error/warning code with default message + hint templates (SPEC §5 taxonomy).
/// E01x lexical · E02x name/scope/info-access · E03x types · E04x structure · W1xx warnings.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Code {
    pub id: &'static str,
    pub severity: Severity,
    pub summary: &'static str,
    pub hint: Option<&'static str>,
}

macro_rules! codes {
    ($($name:ident => ($id:literal, $sev:expr, $summary:literal, $hint:expr);)*) => {
        $(pub const $name: Code = Code { id: $id, severity: $sev, summary: $summary, hint: $hint };)*
        pub const ALL: &[Code] = &[$($name),*];
    };
}

// Initial code registry. M1 exercises the lexical/structure/info-access ones; the type
// codes (E03x) are wired here so typeck can emit them in M2 without a taxonomy change.
codes! {
    E010 => ("E010", Severity::Error, "unrecognized token", None);
    E011 => ("E011", Severity::Error, "unterminated string literal", None);
    E012 => ("E012", Severity::Error, "syntax error", None);
    E020 => ("E020", Severity::Error, "unrevealed information", Some("opponent move sets are hidden; use `revealed_moves` or `revealed(...)`"));
    E021 => ("E021", Severity::Error, "unknown name", None);
    E022 => ("E022", Severity::Error, "unknown predicate", None);
    E023 => ("E023", Severity::Error, "`it` used outside an exists/best binding", None);
    E030 => ("E030", Severity::Error, "condition has type tribool; `when` requires bool", Some("wrap in one of likely(...), worst_case(...), best_case(...)"));
    E031 => ("E031", Severity::Error, "resolver applied to a value that is already a fact", None);
    E032 => ("E032", Severity::Error, "effectiveness is categorical; compare with at_least/at_most", None);
    E040 => ("E040", Severity::Error, "block must end with an `otherwise` rule", Some("add `otherwise:` with a `do` action so the policy is total"));
    E041 => ("E041", Severity::Error, "illegal action for this block", Some("`on forced_switch` allows switch actions only"));
    W100 => ("W100", Severity::Warning, "unreachable rule shadowed by an earlier, more general rule", None);
}

/// A single emitted diagnostic. `message`/`hint` default from the [`Code`] but may be
/// overridden with span-specific detail.
#[derive(Debug, Clone)]
pub struct Diagnostic {
    pub code: Code,
    pub span: Span,
    pub message: String,
    pub hint: Option<String>,
}

impl Diagnostic {
    pub fn new(code: Code, span: Span) -> Self {
        Diagnostic {
            code,
            span,
            message: code.summary.to_string(),
            hint: code.hint.map(str::to_string),
        }
    }
    pub fn with_message(mut self, msg: impl Into<String>) -> Self {
        self.message = msg.into();
        self
    }
    pub fn with_hint(mut self, hint: impl Into<String>) -> Self {
        self.hint = Some(hint.into());
        self
    }
}

/// Source text + filename; maps byte offsets to 1-based line/col for rendering.
pub struct SourceFile {
    pub name: String,
    pub text: String,
    line_starts: Vec<usize>,
}

impl SourceFile {
    pub fn new(name: impl Into<String>, text: impl Into<String>) -> Self {
        let text = text.into();
        let mut line_starts = vec![0];
        for (i, b) in text.bytes().enumerate() {
            if b == b'\n' {
                line_starts.push(i + 1);
            }
        }
        SourceFile { name: name.into(), text, line_starts }
    }

    /// 1-based (line, col) for a byte offset. col counts UTF-8 bytes within the line + 1.
    pub fn line_col(&self, offset: usize) -> (usize, usize) {
        let line = match self.line_starts.binary_search(&offset) {
            Ok(i) => i,
            Err(i) => i - 1,
        };
        (line + 1, offset - self.line_starts[line] + 1)
    }

    pub fn slice(&self, span: Span) -> &str {
        &self.text[span.start..span.end.min(self.text.len())]
    }
}

#[derive(Serialize)]
struct SpanJson<'a> {
    file: &'a str,
    line: usize,
    col: usize,
    len: usize,
}

#[derive(Serialize)]
struct DiagJson<'a> {
    code: &'a str,
    severity: Severity,
    span: SpanJson<'a>,
    message: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    hint: Option<&'a str>,
    docs_tool: String,
}

#[derive(Serialize)]
struct ReportJson<'a> {
    version: &'a str,
    status: &'a str,
    diagnostics: Vec<DiagJson<'a>>,
}

/// Render diagnostics into the `diag.json` document (SPEC §5). `status` is "error" if any
/// error-severity diagnostic is present, else "ok".
pub fn render_report(src: &SourceFile, diags: &[Diagnostic]) -> serde_json::Value {
    let has_error = diags.iter().any(|d| d.code.severity == Severity::Error);
    let items: Vec<DiagJson> = diags
        .iter()
        .map(|d| {
            let (line, col) = src.line_col(d.span.start);
            DiagJson {
                code: d.code.id,
                severity: d.code.severity,
                span: SpanJson { file: &src.name, line, col, len: d.span.len() },
                message: &d.message,
                hint: d.hint.as_deref(),
                docs_tool: format!("explain_error:{}", d.code.id),
            }
        })
        .collect();
    serde_json::to_value(ReportJson {
        version: DIAG_VERSION,
        status: if has_error { "error" } else { "ok" },
        diagnostics: items,
    })
    .expect("diag report serializes")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn line_col_maps_offsets() {
        let src = SourceFile::new("bot.rpo", "abc\ndefg\n");
        assert_eq!(src.line_col(0), (1, 1));
        assert_eq!(src.line_col(4), (2, 1));
        assert_eq!(src.line_col(6), (2, 3));
    }

    #[test]
    fn report_status_reflects_errors() {
        let src = SourceFile::new("bot.rpo", "hello");
        let d = Diagnostic::new(E040, Span::new(0, 5));
        let v = render_report(&src, &[d]);
        assert_eq!(v["status"], "error");
        assert_eq!(v["diagnostics"][0]["code"], "E040");
        assert_eq!(v["diagnostics"][0]["docs_tool"], "explain_error:E040");
    }
}
