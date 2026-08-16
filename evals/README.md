# evals — Riposte-specific eval bindings

The concrete experiment for Riposte. Imports the generic [`../evalkit/`](../evalkit/) and
supplies everything Pokémon/Riposte-specific. See [SPEC.md §7](../SPEC.md).

- `tasks/` — 25–40 natural-language strategy briefs, graded T1–T3.
- `golden/` — reference `.rpo` programs we write; double as the harness smoke test.
- `conditions/` — steering condition configs (C1 docs-dump, C2 progressive-MCP,
  C3 docs+repair, C4 MCP+repair); pinned model versions.
- `analysis/` — notebooks: win-rate + Wilson CIs, the "compiles but loses" gap vs. golden,
  quirk-error profiles.
- Battle orchestration (async, seeded) against baselines: `RandomPlayer`,
  `MaxDamagePlayer`, `SimpleHeuristics` (ours), and each task's golden program.

**Headline metric:** agent-program win rate vs. golden-program win rate on the same task —
the semantic gap that parse/compile metrics can't see.
