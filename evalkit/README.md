# evalkit — the generic toy eval framework

Domain-agnostic scaffolding for agent-steering experiments. **No Riposte or Pokémon
imports may enter this package** — that boundary is what keeps it extractable
(`git subtree split evalkit`) if it proves reusable beyond this project.

Intended surface (built after the DSL, per the DSL → framework → learnings sequence):

- **Driver interface** — abstracts agent invocation so conditions can run against the
  Anthropic API directly or with an MCP server attached.
- **Condition runner** — executes steering conditions (docs-dump / progressive-MCP /
  repair loops) as configs, `k` samples per task.
- **Metrics** — pass@k, repair efficiency, cost (tokens/success), and pluggable
  ground-truth scorers.
- **Model tiering** — frontier + small/cheap model matrix.

Riposte-specific bindings (tasks, golden programs, Showdown battle orchestration,
win-rate scoring) live in [`../evals/`](../evals/), which imports this package.
