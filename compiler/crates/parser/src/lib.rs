//! Hand-written recursive-descent parser (SPEC §4.7, §5). Chosen over a parser generator
//! for full control over error recovery and message quality. On a syntax error it records a
//! diagnostic and synchronizes to the next `rule` / `otherwise` / `on` keyword, so one run
//! reports multiple errors.
//!
//! Precedence (loosest→tightest): `or` < `and` < `not` < infix (comparison, `outspeeds`,
//! `knows`, `at_least`/`at_most`) < primary. `exists … where …` and the resolvers
//! `likely`/`worst_case`/`best_case` are primaries.

use riposte_ast::*;
use riposte_diagnostics::{Diagnostic, Span, E012};
use riposte_lexer::{Spanned, Tok};

pub struct Parsed {
    pub program: Option<Program>,
    pub diags: Vec<Diagnostic>,
}

pub fn parse(src: &str, toks: &[Spanned]) -> Parsed {
    let mut p = Parser { source: src, toks, pos: 0, diags: Vec::new(), src_len: src.len() };
    let program = p.program();
    Parsed { program, diags: p.diags }
}

type PResult<T> = Result<T, ()>;

struct Parser<'a> {
    source: &'a str,
    toks: &'a [Spanned],
    pos: usize,
    diags: Vec<Diagnostic>,
    src_len: usize,
}

impl<'a> Parser<'a> {
    // ── cursor helpers ──
    fn peek(&self) -> Option<Tok> {
        self.toks.get(self.pos).map(|s| s.tok)
    }
    fn at(&self, t: Tok) -> bool {
        self.peek() == Some(t)
    }
    fn span(&self) -> Span {
        self.toks
            .get(self.pos)
            .map(|s| s.span)
            .unwrap_or_else(|| Span::new(self.src_len, self.src_len))
    }
    fn prev_span(&self) -> Span {
        self.toks.get(self.pos.saturating_sub(1)).map(|s| s.span).unwrap_or(self.span())
    }
    fn bump(&mut self) -> Spanned {
        let s = self.toks[self.pos];
        self.pos += 1;
        s
    }
    fn eat(&mut self, t: Tok) -> bool {
        if self.at(t) {
            self.pos += 1;
            true
        } else {
            false
        }
    }
    fn error(&mut self, span: Span, msg: impl Into<String>) {
        self.diags.push(Diagnostic::new(E012, span).with_message(msg));
    }
    fn expect(&mut self, t: Tok, what: &str) -> PResult<Spanned> {
        if self.at(t) {
            Ok(self.bump())
        } else {
            let sp = self.span();
            self.error(sp, format!("expected {what}"));
            Err(())
        }
    }

    /// Skip tokens until a recovery point (a rule/block boundary) so parsing can continue.
    fn synchronize(&mut self) {
        while let Some(t) = self.peek() {
            if matches!(t, Tok::Rule | Tok::Otherwise | Tok::On) {
                return;
            }
            self.pos += 1;
        }
    }

    // ── program / blocks ──
    fn program(&mut self) -> Option<Program> {
        let start = self.span();
        let header = match self.header() {
            Ok(h) => h,
            Err(()) => {
                // header is required; without it, still try to recover blocks
                self.synchronize();
                (Ident { text: String::new(), span: start }, Ident { text: String::new(), span: start })
            }
        };
        let (bot_name, format) = header;

        let mut on_turn = None;
        let mut on_forced_switch = None;
        while self.at(Tok::On) {
            match self.block() {
                Ok(b) => match b.event {
                    Event::Turn => on_turn = Some(b),
                    Event::ForcedSwitch => on_forced_switch = Some(b),
                },
                Err(()) => self.synchronize(),
            }
        }
        if let Some(t) = self.peek() {
            // trailing junk after the last block
            let sp = self.span();
            self.error(sp, format!("unexpected token after program: {t:?}"));
        }
        let end = self.prev_span();
        Some(Program { bot_name, format, on_turn, on_forced_switch, span: start.to(end) })
    }

    fn header(&mut self) -> PResult<(Ident, Ident)> {
        self.expect(Tok::Bot, "`bot`")?;
        let name_tok = self.expect(Tok::Str, "a quoted bot name")?;
        let bot_name = Ident { text: unquote(self.tok_text(name_tok)), span: name_tok.span };
        self.expect(Tok::Format, "`format`")?;
        let fmt_tok = self.expect(Tok::Ident, "a format id (e.g. gen9randombattle)")?;
        let format = Ident { text: self.tok_text(fmt_tok).to_string(), span: fmt_tok.span };
        Ok((bot_name, format))
    }

    fn block(&mut self) -> PResult<Block> {
        let on = self.expect(Tok::On, "`on`")?;
        let event = match self.peek() {
            Some(Tok::Turn) => {
                self.bump();
                Event::Turn
            }
            Some(Tok::ForcedSwitch) => {
                self.bump();
                Event::ForcedSwitch
            }
            _ => {
                let sp = self.span();
                self.error(sp, "expected `turn` or `forced_switch` after `on`");
                return Err(());
            }
        };
        self.expect(Tok::Colon, "`:` after the event")?;

        let mut rules = Vec::new();
        while matches!(self.peek(), Some(Tok::Rule) | Some(Tok::Otherwise)) {
            match self.rule() {
                Ok(r) => rules.push(r),
                Err(()) => self.synchronize(),
            }
        }
        let end = self.prev_span();
        Ok(Block { event, rules, span: on.span.to(end) })
    }

    fn rule(&mut self) -> PResult<Rule> {
        if self.at(Tok::Otherwise) {
            let kw = self.bump();
            self.expect(Tok::Colon, "`:` after `otherwise`")?;
            self.expect(Tok::Do, "`do` and an action")?;
            let action = self.action()?;
            let span = kw.span.to(action.span());
            return Ok(Rule { name: None, when: None, action, span });
        }
        let kw = self.expect(Tok::Rule, "`rule` or `otherwise`")?;
        let name_tok = self.expect(Tok::Ident, "a rule name")?;
        let name = Ident { text: self.tok_text(name_tok).to_string(), span: name_tok.span };
        self.expect(Tok::Colon, "`:` after the rule name")?;
        self.expect(Tok::When, "`when` and a condition")?;
        let when = self.expr()?;
        self.expect(Tok::Do, "`do` and an action")?;
        let action = self.action()?;
        let span = kw.span.to(action.span());
        Ok(Rule { name: Some(name), when: Some(when), action, span })
    }

    // ── actions ──
    fn action(&mut self) -> PResult<Action> {
        match self.peek() {
            Some(Tok::Use) => {
                let kw = self.bump();
                if self.at(Tok::Str) {
                    let m = self.bump();
                    let move_id = Ident { text: unquote(self.tok_text(m)), span: m.span };
                    let tera = self.opt_with_tera();
                    let span = kw.span.to(self.prev_span());
                    Ok(Action::UseMove { move_id, tera, span })
                } else if self.at(Tok::Ident) && self.tok_text(self.toks[self.pos]) == "strongest_move" {
                    self.bump();
                    self.expect(Tok::Against, "`against` and a target")?;
                    let target = self.path()?;
                    let tera = self.opt_with_tera();
                    let span = kw.span.to(self.prev_span());
                    Ok(Action::UseStrongest { target, tera, span })
                } else {
                    let sp = self.span();
                    self.error(sp, "expected a quoted move id or `strongest_move` after `use`");
                    Err(())
                }
            }
            Some(Tok::SwitchTo) => {
                let kw = self.bump();
                self.expect(Tok::Best, "`best` selector")?;
                let dom_tok = self.expect(Tok::Ident, "a domain (e.g. `bench`)")?;
                let domain = Ident { text: self.tok_text(dom_tok).to_string(), span: dom_tok.span };
                self.expect(Tok::By, "`by` and a sort key")?;
                let key = self.expr()?;
                let span = kw.span.to(key.span());
                Ok(Action::Switch { domain, key, span })
            }
            _ => {
                let sp = self.span();
                self.error(sp, "expected an action (`use` or `switch_to`)");
                Err(())
            }
        }
    }

    fn opt_with_tera(&mut self) -> bool {
        if self.at(Tok::With) {
            self.bump();
            // `with tera` — tolerate a missing `tera` by reporting but not failing hard
            if !self.eat(Tok::Tera) {
                let sp = self.span();
                self.error(sp, "expected `tera` after `with`");
            }
            true
        } else {
            false
        }
    }

    // ── expressions (precedence climbing by hand) ──
    fn expr(&mut self) -> PResult<Expr> {
        self.parse_or()
    }

    fn parse_or(&mut self) -> PResult<Expr> {
        let first = self.parse_and()?;
        if !self.at(Tok::Or) {
            return Ok(first);
        }
        let mut operands = vec![first];
        while self.eat(Tok::Or) {
            operands.push(self.parse_and()?);
        }
        let span = operands.first().unwrap().span().to(operands.last().unwrap().span());
        Ok(Expr::Or { operands, span })
    }

    fn parse_and(&mut self) -> PResult<Expr> {
        let first = self.parse_not()?;
        if !self.at(Tok::And) {
            return Ok(first);
        }
        let mut operands = vec![first];
        while self.eat(Tok::And) {
            operands.push(self.parse_not()?);
        }
        let span = operands.first().unwrap().span().to(operands.last().unwrap().span());
        Ok(Expr::And { operands, span })
    }

    fn parse_not(&mut self) -> PResult<Expr> {
        if self.at(Tok::Not) {
            let kw = self.bump();
            let arg = self.parse_not()?;
            let span = kw.span.to(arg.span());
            return Ok(Expr::Not { arg: Box::new(arg), span });
        }
        self.parse_infix()
    }

    /// One optional infix operator between two primaries (non-associative).
    fn parse_infix(&mut self) -> PResult<Expr> {
        let left = self.parse_primary()?;
        match self.peek() {
            Some(Tok::Outspeeds) => {
                self.bump();
                let right = self.parse_primary()?;
                let span = left.span().to(right.span());
                Ok(Expr::Outspeeds { left: Box::new(left), right: Box::new(right), span })
            }
            Some(Tok::Knows) => {
                self.bump();
                let right = self.parse_primary()?;
                let span = left.span().to(right.span());
                Ok(Expr::Knows { mon: Box::new(left), move_lit: Box::new(right), span })
            }
            Some(Tok::AtLeast) | Some(Tok::AtMost) => {
                let op = if self.at(Tok::AtLeast) { EffOp::AtLeast } else { EffOp::AtMost };
                self.bump();
                let cat_tok = self.expect(Tok::Ident, "an effectiveness category")?;
                let cat = Ident { text: self.tok_text(cat_tok).to_string(), span: cat_tok.span };
                let span = left.span().to(cat.span);
                Ok(Expr::EffCompare { op, left: Box::new(left), cat, span })
            }
            Some(t) if cmp_op(t).is_some() => {
                let op = cmp_op(t).unwrap();
                self.bump();
                let right = self.parse_primary()?;
                let span = left.span().to(right.span());
                Ok(Expr::Compare { op, left: Box::new(left), right: Box::new(right), span })
            }
            _ => Ok(left),
        }
    }

    fn parse_primary(&mut self) -> PResult<Expr> {
        match self.peek() {
            Some(Tok::LParen) => {
                self.bump();
                let e = self.expr()?;
                self.expect(Tok::RParen, "`)`")?;
                Ok(e)
            }
            Some(Tok::Likely) | Some(Tok::WorstCase) | Some(Tok::BestCase) => self.resolver(),
            Some(Tok::Exists) => self.exists(),
            Some(Tok::Str) => {
                let s = self.bump();
                Ok(Expr::Str(Ident { text: unquote(self.tok_text(s)), span: s.span }))
            }
            Some(Tok::Int) | Some(Tok::Float) => {
                let is_float = self.at(Tok::Float);
                let n = self.bump();
                Ok(Expr::Num { raw: self.tok_text(n).to_string(), is_float, span: n.span })
            }
            Some(Tok::Ident) | Some(Tok::It) => Ok(Expr::Path(self.path()?)),
            _ => {
                let sp = self.span();
                self.error(sp, "expected an expression");
                Err(())
            }
        }
    }

    fn resolver(&mut self) -> PResult<Expr> {
        let op = match self.peek() {
            Some(Tok::Likely) => ResolveOp::Likely,
            Some(Tok::WorstCase) => ResolveOp::WorstCase,
            _ => ResolveOp::BestCase,
        };
        let kw = self.bump();
        self.expect(Tok::LParen, "`(` after the resolver")?;
        let arg = self.expr()?;
        let close = self.expect(Tok::RParen, "`)` to close the resolver")?;
        let span = kw.span.to(close.span);
        Ok(Expr::Resolve { op, arg: Box::new(arg), span })
    }

    fn exists(&mut self) -> PResult<Expr> {
        let kw = self.expect(Tok::Exists, "`exists`")?;
        let dom_tok = self.expect(Tok::Ident, "a domain (e.g. `bench`)")?;
        let domain = Ident { text: self.tok_text(dom_tok).to_string(), span: dom_tok.span };
        let var_tok = self.expect(Tok::Ident, "a binder name")?;
        let var = Ident { text: self.tok_text(var_tok).to_string(), span: var_tok.span };
        self.expect(Tok::Where, "`where` and a predicate")?;
        let body = self.expr()?;
        let span = kw.span.to(body.span());
        Ok(Expr::Exists { domain, var, body: Box::new(body), span })
    }

    /// A dotted path where any segment may be a call: `opponent.side.has_hazard(x)`,
    /// `matchup_score(it, opponent.active)`, `my.active.hp_fraction`, `it`.
    fn path(&mut self) -> PResult<Path> {
        let mut segs = Vec::new();
        segs.push(self.seg()?);
        while self.at(Tok::Dot) {
            self.bump();
            segs.push(self.seg()?);
        }
        let span = segs.first().unwrap().span.to(segs.last().unwrap().span);
        Ok(Path { segs, span })
    }

    fn seg(&mut self) -> PResult<Seg> {
        let name_tok = match self.peek() {
            Some(Tok::Ident) | Some(Tok::It) => self.bump(),
            _ => {
                let sp = self.span();
                self.error(sp, "expected a name");
                return Err(());
            }
        };
        let name = Ident { text: self.tok_text(name_tok).to_string(), span: name_tok.span };
        let mut span = name_tok.span;
        let call = if self.at(Tok::LParen) {
            self.bump();
            let mut args = Vec::new();
            if !self.at(Tok::RParen) {
                loop {
                    args.push(self.expr()?);
                    if !self.eat(Tok::Comma) {
                        break;
                    }
                }
            }
            let close = self.expect(Tok::RParen, "`)` to close the argument list")?;
            span = span.to(close.span);
            Some(args)
        } else {
            None
        };
        Ok(Seg { name, call, span })
    }

    // ── token text ──
    fn tok_text(&self, s: Spanned) -> &'a str {
        &self.source[s.span.start..s.span.end]
    }
}

/// Strip surrounding double quotes from a string-literal lexeme.
fn unquote(lexeme: &str) -> String {
    lexeme.trim_matches('"').to_string()
}

fn cmp_op(t: Tok) -> Option<CmpOp> {
    Some(match t {
        Tok::Eq => CmpOp::Eq,
        Tok::Ne => CmpOp::Ne,
        Tok::Lt => CmpOp::Lt,
        Tok::Le => CmpOp::Le,
        Tok::Gt => CmpOp::Gt,
        Tok::Ge => CmpOp::Ge,
        _ => return None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use riposte_lexer::lex;

    fn parse_str(src: &str) -> Parsed {
        let (toks, ldiags) = lex(src);
        assert!(ldiags.is_empty(), "unexpected lex errors: {ldiags:?}");
        parse(src, &toks)
    }

    #[test]
    fn parses_spec_example_cleanly() {
        let src = include_str!("../../../../examples/hazard_control.rpo");
        let out = parse_str(src);
        assert!(out.diags.is_empty(), "unexpected parse diags: {:?}", out.diags);
        let prog = out.program.expect("program");
        assert_eq!(prog.bot_name.text, "hazard_control");
        assert_eq!(prog.format.text, "gen9randombattle");
        let turn = prog.on_turn.expect("on turn block");
        assert_eq!(turn.rules.len(), 4); // 3 rules + otherwise
        assert_eq!(turn.rules[0].name.as_ref().unwrap().text, "lead_hazards");
        assert!(turn.rules[3].name.is_none()); // otherwise
        let fs = prog.on_forced_switch.expect("forced_switch block");
        assert_eq!(fs.rules.len(), 2);
    }

    #[test]
    fn recovers_and_reports_multiple_errors() {
        // two broken rules; parser should sync on `rule`/`otherwise` and report both.
        let src = "bot \"x\" format gen9randombattle\n\
                   on turn:\n\
                   rule a: when @@@ do use \"tackle\"\n\
                   rule b: when likely(can_ko(my.active, opponent.active)) do %%%\n\
                   otherwise: do use strongest_move against opponent.active\n";
        let (toks, _ldiags) = lex(src);
        let out = parse(src, &toks);
        assert!(out.diags.len() >= 2, "expected >=2 diags, got {:?}", out.diags);
        // still recovers a program with the otherwise rule
        let prog = out.program.expect("program");
        let turn = prog.on_turn.expect("turn");
        assert!(turn.rules.iter().any(|r| r.name.is_none()));
    }
}
