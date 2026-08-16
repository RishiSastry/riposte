# Steering-delivery findings — v1 (bounded matrix)

First real pass at the question the project exists to answer: **given a language no LLM has
seen, which steering *delivery* teaches an agent to write correct, competitive programs?**

**This is a small, noisy first run — directional, not conclusive.** 3 tasks × 3 conditions ×
2 models × k=1, graded on N=40 battles vs poke-env's `SimpleHeuristicsPlayer`. Raw data:
[`../evals/results/`](../evals/results/). Reproduce with `python evals/experiment.py`.

## Conditions (the independent variable)

| | delivery | compiler-feedback repair loop |
|---|---|---|
| **C1-docs** | full language reference dumped into the prompt, one shot | no |
| **C2-mcp** | seed prompt + MCP discovery tools the agent explores | no |
| **C4-mcp-repair** | seed + MCP tools incl. `check_program` | yes (≤3 rounds) |

All three derive their *content* from the same `steering/` source — they differ only in
delivery.

## Results (aggregated by condition, across tasks + models)

| condition | compile-pass | avg quirk-violations | win-rate (of compiled) | avg tokens |
|---|---|---|---|---|
| **C1-docs** | 83% | **0.0** | 46% | **20.2K** |
| **C2-mcp** | **100%** | **0.0** | 48% | 34.0K |
| **C4-mcp-repair** | **100%** | **0.0** | 41% | 43.4K |

Models: `claude-opus-4-8` (frontier) and `claude-haiku-4-5` (cheap). Repair loop was actually
used — C4 averaged 1.2 `check_program` calls/cell (C1/C2: 0, no compile tool exposed).

## What this suggests

1. **Quirk-learning is essentially solved by good steering — the interesting failures are
   elsewhere.** Zero quirk violations (E030/E031/E032/E040/E041) across all 17 compiled
   programs, under *both* docs-dump and MCP delivery. Agents consistently got facts-vs-
   estimates, mandatory resolvers, and categorical effectiveness right. The `steering/`
   content lands; the "can't express the lie" design isn't tripping anyone up who read it.

2. **MCP delivery bought reliability over one-shot docs — but the gap was basic validity, not
   quirks.** The only non-compile was `haiku × C1-docs` on the hardest task, and it wasn't a
   quirk error — the model invented `when true` (Riposte has no boolean literal):

   ```
   rule press_advantage:
     when true                      # ← not valid Riposte; no compiler feedback to catch it
     do use strongest_move against opponent.active
   ```

   MCP conditions hit 100% compile. Two plausible reasons, not yet separated: discovery keeps
   the model grounded in real syntax, and C4's repair loop would have caught this on the first
   `check_program` call. A one-shot from docs on a weaker model has neither safety net.

3. **Cost orders cleanly: docs-dump < MCP < MCP+repair** (20K → 34K → 43K tokens). MCP
   discovery costs ~1.7× the docs-dump; the repair loop adds ~1.3× on top. So the reliability
   of MCP+repair is not free — for a frontier model that rarely errs, the cheaper docs-dump is
   attractive; for a weaker/cheaper model, MCP's grounding may pay for itself.

4. **Win-rate didn't separate the conditions here** (41–48%, well inside the ±15% noise band
   at N=40, k=1). Notably, several LLM-written programs beat our hand-written golden's ~37% vs
   the same baseline — the agents are writing genuinely competitive policies, not just
   compilable ones. Teasing apart the "compiles but loses" gap needs more samples and N.

## Caveats / next

- k=1 and N=40 make per-cell win-rates noisy; the condition averages are steadier but still
  directional. Bump k and N (SPEC targets N=200 with Wilson CIs) before drawing win-rate
  conclusions.
- Only 3 tasks; the SPEC task set is 25–40. More tasks, especially higher-tier (T3) ones that
  need bench quantifiers and est-resolution, will stress the delivery modes harder.
- C3 (docs + repair) not run here — it would isolate whether C1's failures are *delivery*
  (docs vs discovery) or *lack of a repair loop*. That's the crisp next experiment: if
  C3 ≈ 100% compile like C4, the win is repair; if it stays at C1's level, the win is
  discovery.
