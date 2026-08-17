# Riposte

A tiny declarative language for Pokémon battle policies that no LLM has ever seen. A Riposte
program compiles (Rust) to a JSON policy IR that a Python runtime plays on a real
[Pokémon Showdown](https://github.com/smogon/pokemon-showdown) server via
[poke-env](https://poke-env.readthedocs.io). It exists as an **instrument**: a clean way to
measure how you best teach a coding agent a language it has never seen, graded not by an
LLM-as-judge but by whether the program **compiles** and **wins real battles**.

The write-up that motivates it: [**How I evaluate coding agents that write DSLs**](./writeup/agent-evals-for-dsls.md).
Design rationale: [SPEC.md](./SPEC.md). Engineering tour: [GUIDE.md](./GUIDE.md).

## A program

```
bot "hazard_control" format gen9randombattle

on turn:
  rule escape_bad_matchup:
    when worst_case(opponent.active outspeeds my.active)
         and likely(can_ko(opponent.active, my.active))
         and exists bench b where resists(b, opponent.active.primary_type)
    do switch_to best bench by matchup_score(it, opponent.active)

  rule press_advantage:
    when likely(can_ko(my.active, opponent.active))
    do use strongest_move against opponent.active

  otherwise:
    do use strongest_move against opponent.active
```

The type system separates **facts** (what you know) from **estimates** (the opponent's hidden
stats), so a comparison over an estimate is a `tribool` that *must* be resolved with
`likely` / `worst_case` / `best_case`. Treating a guess as a certainty does not compile. Peeking
at hidden state has no syntax at all.

## The result (not the one I expected)

I built this to measure one thing: whether docs in the prompt or discovery through MCP tools
teaches the language better. The sharper answer turned out to be about neither. The harness
varies *how the language is taught* to an agent (docs vs. MCP discovery, each with and without
a compiler-feedback repair loop) and grades what the agent writes:

| how the language was taught | compile-pass | quirk violations | win-rate | avg tokens |
|---|---|---|---|---|
| docs, one-shot | 83% | 0.11 | 45% | 21K |
| tool-discovery, one-shot | 89% | 0.06 | 42% | 35K |
| docs + repair loop | **100%** | **0.0** | 44% | 31K |
| tool-discovery + repair loop | **100%** | **0.0** | 44% | 48K |

> **Illustrative, not settled.** 3 tasks × 4 conditions × 2 models (Claude Opus, Haiku) × k=3 =
> 72 runs, one pass, win-rate over 60 battles vs. a heuristic baseline. The spec targets 25–40
> tasks; compile-pass CIs are correspondingly wide (see [findings](./writeup/findings.md)). Read
> it as a demo of the harness.

Directionally: a compiler-feedback repair loop moved compile reliability more than the delivery
channel did, and reached it for fewer tokens when paired with docs. Once a program was valid,
competitive quality was flat across conditions. Full numbers, per-model splits, and Wilson CIs
in [`writeup/findings.md`](./writeup/findings.md).

## Quickstart

```bash
# 1. build the compiler and compile a program to its IR
cargo build --manifest-path compiler/Cargo.toml
compiler/target/debug/riposte-c build examples/hazard_control.rpo --stdout

# 2. run the eval harness (stub agent, no API key needed)
pip install -e evalkit -e evals
evalkit run evals/features/hazard_control.feature --steps riposte_evals.steps \
  --driver stub --stub-source examples/hazard_control.rpo

# 3. reproduce the experiment above (needs evalkit[agent] + ANTHROPIC_API_KEY + local Showdown)
python evals/experiment.py
```

Running the app end-to-end (local Showdown server, a hand-written policy that wins ~99% vs
`RandomPlayer` and ~37% vs `SimpleHeuristics`, the same baseline the agents score ~44% against)
and the full architecture are in [GUIDE.md](./GUIDE.md).

## What's here

| Path | What's here |
|------|-------------|
| [`compiler/`](./compiler) | The DSL compiler (Rust): lexer, parser, epistemic type system (the fact/est checks), IR emit, first-class `diag.json`. |
| [`runtime/`](./runtime) | Interprets the compiled IR and plays battles via poke-env. |
| [`mcp/`](./mcp) · [`steering/`](./steering) | The MCP discovery server + the language docs it serves (one source, two delivery modes). |
| [`evalkit/`](./evalkit) · [`evals/`](./evals) | The eval framework: async Gherkin runner + `deepagents` agent driver, and the Riposte grading. |
| [`examples/agent_demo/`](./examples/agent_demo) | A real transcript of a model discovering the language via MCP and writing a winning bot. |
| [`writeup/`](./writeup) | The essay and the raw findings. |
