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
| `evalkit/`   | **Generic** eval framework: driver interface, condition runner, metrics, model tiering. No Pokémon/Riposte imports. |
| `evals/`     | **Riposte-specific**: task briefs, golden `.rpo` programs, baselines, battle orchestration. Imports `evalkit`. |
| `examples/`  | Example `.rpo` programs.                                               |
| `writeup/`   | Eval-learnings post; references exact commits/artifacts.               |

## Status

Pre-M0. Scaffold only. Next: **M0 — walking skeleton** (local Showdown running; a
hand-written `policy.json` interpreted by a minimal `RipostePlayer` that beats
`RandomPlayer` >70% over 100 battles). No Rust until battles run locally.

See [SPEC.md §9](./SPEC.md) for milestones M0–M5.
