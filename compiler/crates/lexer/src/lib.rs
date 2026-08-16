//! Lexer (SPEC §4.7). Keywords are the fixed set from the grammar sketch; everything else
//! alphanumeric is an `Ident` resolved contextually by the parser (`bench`, `strongest_move`,
//! effectiveness categories like `super`/`neutral` are NOT keywords). Whitespace and `#`
//! line comments are skipped — Riposte is not indentation-sensitive; keywords delimit.

use logos::Logos;
use riposte_diagnostics::{Diagnostic, Span, E010, E011};

#[derive(Logos, Debug, Clone, Copy, PartialEq, Eq)]
#[logos(skip r"[ \t\r\n\f]+")]
#[logos(skip r"#[^\n]*")]
pub enum Tok {
    // ── keywords (§4.7) ──
    #[token("bot")] Bot,
    #[token("format")] Format,
    #[token("on")] On,
    #[token("turn")] Turn,
    #[token("forced_switch")] ForcedSwitch,
    #[token("rule")] Rule,
    #[token("otherwise")] Otherwise,
    #[token("when")] When,
    #[token("do")] Do,
    #[token("and")] And,
    #[token("or")] Or,
    #[token("not")] Not,
    #[token("exists")] Exists,
    #[token("where")] Where,
    #[token("use")] Use,
    #[token("switch_to")] SwitchTo,
    #[token("best")] Best,
    #[token("by")] By,
    #[token("against")] Against,
    #[token("with")] With,
    #[token("tera")] Tera,
    #[token("likely")] Likely,
    #[token("worst_case")] WorstCase,
    #[token("best_case")] BestCase,
    #[token("at_least")] AtLeast,
    #[token("at_most")] AtMost,
    #[token("it")] It,
    #[token("outspeeds")] Outspeeds,
    #[token("knows")] Knows,

    // ── comparison operators ──
    #[token("=")] Eq,
    #[token("!=")] Ne,
    #[token("<=")] Le,
    #[token(">=")] Ge,
    #[token("<")] Lt,
    #[token(">")] Gt,

    // ── punctuation ──
    #[token(".")] Dot,
    #[token(",")] Comma,
    #[token(":")] Colon,
    #[token("(")] LParen,
    #[token(")")] RParen,

    // ── literals / names ──
    #[regex(r"[0-9]+\.[0-9]+")] Float,
    #[regex(r"[0-9]+")] Int,
    #[regex(r#""[^"\n]*""#)] Str,
    #[regex(r"[A-Za-z_][A-Za-z0-9_]*")] Ident,
}

/// A token with its byte span.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Spanned {
    pub tok: Tok,
    pub span: Span,
}

/// Lex `src`, returning tokens and any lexical diagnostics. Errors are recovered (the bad
/// byte is skipped) so lexing always yields a full token stream for the parser.
pub fn lex(src: &str) -> (Vec<Spanned>, Vec<Diagnostic>) {
    let mut toks = Vec::new();
    let mut diags = Vec::new();
    let mut lx = Tok::lexer(src);
    while let Some(res) = lx.next() {
        let r = lx.span();
        let span = Span::new(r.start, r.end);
        match res {
            Ok(tok) => toks.push(Spanned { tok, span }),
            Err(_) => {
                // Distinguish an unterminated string (starts with `"`) from a stray byte.
                let code = if src[r.start..].starts_with('"') { E011 } else { E010 };
                diags.push(Diagnostic::new(code, span));
            }
        }
    }
    (toks, diags)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keywords_beat_idents() {
        let (toks, diags) = lex("bot when otherwise foo");
        assert!(diags.is_empty());
        let kinds: Vec<Tok> = toks.iter().map(|t| t.tok).collect();
        assert_eq!(kinds, vec![Tok::Bot, Tok::When, Tok::Otherwise, Tok::Ident]);
    }

    #[test]
    fn lexes_example_header() {
        let (toks, diags) = lex(r#"bot "hazard_control" format gen9randombattle"#);
        assert!(diags.is_empty());
        assert_eq!(toks[0].tok, Tok::Bot);
        assert_eq!(toks[1].tok, Tok::Str);
        assert_eq!(toks[2].tok, Tok::Format);
        assert_eq!(toks[3].tok, Tok::Ident);
    }

    #[test]
    fn comments_and_ops() {
        let (toks, diags) = lex("a >= 2  # comment\n b != 0.5");
        assert!(diags.is_empty());
        let kinds: Vec<Tok> = toks.iter().map(|t| t.tok).collect();
        assert_eq!(
            kinds,
            vec![Tok::Ident, Tok::Ge, Tok::Int, Tok::Ident, Tok::Ne, Tok::Float]
        );
    }

    #[test]
    fn unterminated_string_is_e011() {
        let (_toks, diags) = lex("\"abc");
        assert_eq!(diags.len(), 1);
        assert_eq!(diags[0].code.id, "E011");
    }
}
