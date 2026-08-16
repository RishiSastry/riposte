# Riposte

A small declarative language for expressing Pokémon battle decision policies. A Riposte
program compiles to a deterministic policy that plays real battles on
[Pokémon Showdown](https://github.com/smogon/pokemon-showdown) via
[poke-env](https://poke-env.readthedocs.io).

No model has ever seen this language — which is the point. Riposte is the instrument for
one question:

> **Given a language an LLM has never seen, which steering strategy best teaches an agent
> to write correct, competitive programs in it?**

Full design in [SPEC.md](./SPEC.md).

## Why this repo is a monorepo

The three deliverables — the **DSL**, a **toy eval framework**, and the **learnings**
writeup — co-evolve fastest right now, share a single `steering/` source of truth, and
tell one narrative (the post is about evals; the DSL is the running example). They live
together so changes stay atomic and the writeup can reference exact artifacts.

The seam that keeps this from calcifying: `evalkit/` (generic, reusable — no Riposte
imports) is kept separate from `evals/` (Riposte-specific bindings). If the toy framework
proves reusable, it can be `git subtree split` out later with full history.

## Layout

| Path         | What lives here                                                        |
|--------------|------------------------------------------------------------------------|
| `compiler/`  | Rust workspace `riposte-c`: lex → parse → typeck → emit; `diag.json`.   |
| `runtime/`   | `riposte-rt` (Python): thin interpreter over the JSON policy IR + poke-env Player. |
| `mcp/`       | `riposte-mcp`: progressive language-discovery MCP server.              |
| `steering/`  | Language docs in three grains — single source for C1 docs & C2 MCP.    |
| `evalkit/`   | **Generic** eval framework: custom Gherkin runner, `deepagents`+MCP driver, step registry, CLI. No Pokémon/Riposte imports. |
| `evals/`     | **Riposte-specific**: `.feature` task briefs, step definitions (compile/win-rate/quirks), baselines. Imports `evalkit`. |
| `examples/`  | Example `.rpo` programs.                                               |
| `writeup/`   | Eval-learnings post; references exact commits/artifacts.               |

## Status

The **DSL and MCP server are built**; the eval kit is deferred (build order: DSL → MCP →
eval kit).

- **M0** walking skeleton ✅ — runtime interprets a hand-written IR; beats `RandomPlayer` 99%.
- **M1** compiler front end ✅ — lexer, recursive-descent parser + recovery, AST,
  `GRAMMAR.ebnf`, `diag.json`.
- **M2** type system + predicates ✅ — fact/est + `tribool` + resolvers (E030–E034); real
  gen-9 damage calc; shared `predicates.toml`. Compiler output validates against the runtime
  schema *and* plays real battles.
- **MCP** ✅ — `riposte-mcp` serves the `steering/` grains (`language_overview`, `get_topic`,
  `predicate_reference`, `explain_error`, `check_program`).
- **Eval framework** ✅ — `evalkit` runs **Gherkin `.feature`** evals against a **LangChain
  `deepagents`** agent wired to the `riposte-mcp` executable; grades compile-pass, win rate vs
  baselines, and a quirk-violation budget. Domain-agnostic core + Riposte step defs in `evals/`.

Try it:

```bash
cargo build --manifest-path compiler/Cargo.toml
compiler/target/debug/riposte-c build examples/hazard_control.rpo --stdout   # → policy.json
```

See [SPEC.md §9](./SPEC.md) for the full milestone map (M3 eval harness, M4 full matrix, M5 post).
