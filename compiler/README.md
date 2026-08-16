# riposte-c — the Riposte compiler

Rust workspace. Pipeline (SPEC §5): **lex → parse (with recovery) → name/scope+structure
check → emit**. Emits a JSON policy IR (`policy.json`) — never Python code — and always a
`diag.json`. [`GRAMMAR.ebnf`](./GRAMMAR.ebnf) is the authoritative grammar, kept in sync
with the hand-written parser.

| Crate                | Role                                                                 |
|----------------------|---------------------------------------------------------------------|
| `diagnostics`        | Spans, error-code registry, `diag.json` renderer.                   |
| `lexer`              | logos tokenizer (keywords per §4.7; else `Ident`).                  |
| `ast`                | Syntax tree (spans on every node; no type info).                    |
| `parser`             | Hand-written recursive descent; recovers on `rule`/`otherwise`/`on`.|
| `typeck`             | Name/scope + structure + **M2 epistemic types** (fact/est, tribool). |
| `emit`               | Lower AST → `policy.json` IR (mirrors `runtime/riposte_rt/ir.py`).   |
| `riposte-c`          | CLI + `compile()` library entry point.                              |

## Build & use

```bash
cargo build --release
./target/release/riposte-c build ../examples/hazard_control.rpo --stdout
# writes hazard_control.policy.json + hazard_control.diag.json next to the source
```

## Status: M1 + M2 complete ✓

- Lexer, recursive-descent parser with error recovery, AST, `GRAMMAR.ebnf`.
- `diag.json` with stable codes/spans/hints and the `docs_tool` MCP hook.
- Name/scope + structure checks: **E020** (unrevealed info), **E022** (unknown predicate),
  **E023** (unbound `it`), **E040** (missing `otherwise`), **E041** (illegal action).
- **M2 epistemic type system**: fact/est propagation, `tribool` + mandatory resolvers
  (**E030** unresolved tribool, **E031** redundant resolver), categorical effectiveness
  (**E032**), predicate calls checked against the shared **`predicates.toml`** (**E022**/
  **E033** type / **E034** arity). "Can't express the lie": peeking is unrepresentable and
  treating uncertainty as certainty is a static error.
- Compiles the SPEC §4.1 example to IR; the output **validates against the runtime pydantic
  schema** and **plays real battles** with the runtime's gen-9 damage calc.
- Golden snapshot tests (`insta`) for all diagnostics incl. the quirks; `cargo insta review`.

## M3+ (deferred per build order: DSL → MCP → eval kit)

Next up is the MCP server (progressive language discovery). The eval harness/kit comes last.
