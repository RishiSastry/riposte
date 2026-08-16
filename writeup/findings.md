# Steering-delivery findings

The question the project exists to answer: **given a language no LLM has seen, which steering
strategy best teaches an agent to write correct, competitive programs in it?**

**Setup.** 3 tasks × 4 conditions × 2 models × k=3 = **72 agent runs**, each graded on 60
battles vs poke-env's `SimpleHeuristicsPlayer`. Win-rate CIs are pooled over all battles of a
condition's compiled programs (~1,000 each → tight); compile-pass CIs are over the 18 cells
per condition. All ran concurrently in one event loop in **214 s (~$12)**. Raw per-cell data:
[`../evals/results/`](../evals/results/). Reproduce: `python evals/experiment.py --k 3 --n 60`.

## Conditions (the independent variable)

|  | delivery | compiler-feedback repair loop |
|---|---|---|
| **C1-docs** | full reference dumped into the prompt, one shot | no |
| **C2-mcp** | seed + MCP discovery tools the agent explores | no |
| **C3-docs-repair** | docs **+** a `check_program` compile tool | yes (≤3) |
| **C4-mcp-repair** | MCP tools incl. `check_program` | yes (≤3) |

All four derive their *content* from the same `steering/` source — they differ only in
delivery and whether a repair loop is available.

## Results — by condition (pooled over tasks + models)

| condition | compile-pass [95% CI] | avg quirk-violations | win-rate [95% CI] | avg tokens |
|---|---|---|---|---|
| **C1-docs** | 83% [61–94] | 0.111 | 45% [42–48] | **21.5K** |
| **C2-mcp** | 89% [67–97] | 0.056 | 42% [39–46] | 34.9K |
| **C3-docs-repair** | **100% [82–100]** | **0.0** | 44% [41–47] | 31.3K |
| **C4-mcp-repair** | **100% [82–100]** | **0.0** | 44% [41–47] | 48.1K |

### By condition × model (the tiering split)

| condition | model | compile-pass | quirk-viol. | win-rate | tokens |
|---|---|---|---|---|---|
| C1-docs | haiku-4.5 | 67% | 0.222 | 41% | 17.5K |
| C1-docs | opus-4.8 | **100%** | 0.0 | 48% | 25.4K |
| C2-mcp | haiku-4.5 | 89% | 0.111 | 43% | 33.6K |
| C2-mcp | opus-4.8 | 89% | 0.0 | 42% | 36.3K |
| C3-docs-repair | haiku-4.5 | 100% | 0.0 | 44% | 32.0K |
| C3-docs-repair | opus-4.8 | 100% | 0.0 | 44% | 30.6K |
| C4-mcp-repair | haiku-4.5 | 100% | 0.0 | 43% | 49.7K |
| C4-mcp-repair | opus-4.8 | 100% | 0.0 | 45% | 46.5K |

## Findings

1. **The repair loop — not the delivery channel — is what makes programs reliably correct.**
   Both repair conditions (C3, C4) reach **100% compile-pass and 0 quirk violations**; both
   no-repair conditions (C1, C2) leak. Every one of the 5 non-compiles was a no-repair cell,
   and they include *quirk/structure* failures (`E030` unresolved tribool, `E040` missing
   `otherwise`) — exactly the errors the language is designed to catch. Crucially,
   **C3 (docs + repair) ties C4 (MCP + repair)** on both metrics: the mechanism is the ability
   to compile-check and fix, not how the language was taught. Discovery alone (C2) nudged
   compile-pass over docs alone (C1: 83→89%) but didn't close the gap — repair did.

2. **Docs + repair is the cost-efficient sweet spot.** Token cost orders
   C1-docs (21K) < C3-docs-repair (31K) < C2-mcp (35K) < C4-mcp-repair (48K). C3 buys the same
   100% / 0-quirk reliability as C4 for **~35% fewer tokens** — MCP discovery adds cost without
   adding reliability *beyond what the repair loop already provides*. (MCP's value is
   elsewhere — extensibility, huge tool/doc sets that don't fit a prompt — not measured here.)

3. **Steering affects validity, not competitive quality.** Win-rate is flat across all four
   conditions (42–45%, non-overlapping-with-nothing tight CIs) — once a program is valid, how
   *well* it plays is set by the model's Pokémon reasoning, not the steering channel. And the
   agents are genuinely competitive: ~44% vs `SimpleHeuristics`, at or above our hand-written
   golden's ~37% on the same baseline.

4. **The cheaper the model, the more the repair loop matters — the tiering payoff.** Opus is
   already ~100% compile from a one-shot docs-dump (C1); the failures and residual quirk errors
   concentrate in **haiku**, whose C1 compile-pass is only 67% (quirk-violations 0.222) and
   which is lifted to 100% / 0 by the repair loop. Practical read: for a frontier model, the
   cheapest option (docs-dump, no tools) is nearly as good; for a cheap model, spend on the
   repair loop, not on discovery.

5. **Quirk-learning is largely solved by content + a repair loop.** No compiled program under
   any condition committed a quirk violation once repair was available; the only quirk errors
   anywhere were in no-repair *cheap-model* cells. The `steering/` content teaches the quirks;
   the compiler's structured diagnostics + a repair loop clean up the rest.

## Caveats

- 3 tasks (SPEC targets 25–40), `gen9randombattle` only, one run. Compile-pass/quirk numbers
  are solid (18 cells/condition); win-rate CIs are tight from pooling but the *task set* is
  small, so treat the flat win-rate as "no large effect," not "provably no effect."
- `check_program` availability is the whole repair mechanism; we did not vary the repair-round
  cap (fixed ≤3; observed ~1.1–1.3 used).

## So what does this say about the thesis?

The headline "which steering strategy" has a sharper answer than "MCP vs docs": **a
compiler-feedback repair loop dominates the delivery channel.** Given a language with good
structured diagnostics (which the whole "diagnostics as a first-class output" design buys
you), the cheapest reliable recipe is **docs-dump + repair**, and the benefit of the loop is
concentrated where you'd most want to save money — the cheap model.
