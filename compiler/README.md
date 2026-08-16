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
| `typeck`             | **M1: name/scope + structure checks.** Epistemic types are M2.       |
| `emit`               | Lower AST → `policy.json` IR (mirrors `runtime/riposte_rt/ir.py`).   |
| `riposte-c`          | CLI + `compile()` library entry point.                              |

## Build & use

```bash
cargo build --release
./target/release/riposte-c build ../examples/hazard_control.rpo --stdout
# writes hazard_control.policy.json + hazard_control.diag.json next to the source
```

## Status: M1 complete ✓

- Lexer, recursive-descent parser with error recovery, AST, `GRAMMAR.ebnf`.
- `diag.json` with stable codes/spans/hints and the `docs_tool` MCP hook.
- Name/scope + structure checks: **E020** (unrevealed info), **E022** (unknown predicate),
  **E023** (unbound `it`), **E040** (missing `otherwise`), **E041** (illegal action in
  `forced_switch`). Types are **stubbed** (E030/E031/E032 wired but inert until M2).
- Compiles the SPEC §4.1 example to IR; the output **validates against the runtime pydantic
  schema** (the compiler↔runtime contract).
- Golden snapshot tests (`insta`) for diagnostics; `cargo insta review` to update.

## M2 (next)

fact/est propagation, `tribool` + resolver checking (E030/E031), categorical effectiveness
(E032), and a shared `predicates.toml` so the Rust signatures and the Python runtime
implementations can't drift.
