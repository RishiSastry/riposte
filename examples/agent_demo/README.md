# Watch a model learn Riposte

A real run of the eval framework. **Claude Opus 4.8, which has never seen Riposte**, was given
one natural-language brief and the `riposte-mcp` discovery tools — nothing else. In **28
seconds** it discovered the language, wrote a program, compiled it clean on the **first
`check_program` call**, and the program won **49/50 battles vs `RandomPlayer`**.

- Model: `claude-opus-4-8` · condition: `mcp-repair` (may repair against compiler diagnostics)
- 13 MCP tool calls · compile status: **ok, 0 diagnostics** · win rate: **49/50 (98%)**

## The brief it was given

> Write a Riposte bot that keeps entry hazards up — set Stealth Rock when your active mon knows
> it and the opponent's side doesn't already have it — pivots out of bad matchups when the
> opponent is faster and likely to KO you, and presses the attack when you have a clear KO.

## How it discovered the language (actual tool-call sequence)

The agent walked the steering grains methodically *before* writing a line — exactly the
progressive-discovery behavior the experiment measures:

```
1.  language_overview()                       # the program shape, the two blocks
2.  list_topics()                             # what's available
3.  get_topic(types_and_estimates)            # facts vs estimates, tribool, resolvers
4.  get_topic(quirks)                          # the four deliberate quirks
5.  get_topic(state_surface)                   # what it can read
6.  get_topic(predicates)
7.  get_topic(actions)
8.  get_topic(selectors)
9.  get_topic(worked_example_offensive)
10. get_topic(worked_example_defensive)
11. predicate_reference(can_ko)                # confirm the tribool return
12. predicate_reference(outspeeds)             # confirm the tribool return
13. check_program(...)                         # compiled clean — no repair needed
```

(Full data, including argument summaries, in [`run.json`](./run.json).)

## The program it wrote → [`hazard_keeper.rpo`](./hazard_keeper.rpo)

It got **all four quirks right** — the thing an agent that skimmed vs. one that read the
steering diverge on:

- `my.active knows "stealthrock"` — `knows` is a **fact**, so **no resolver** (avoids E031).
- `likely(can_ko(...))` and `worst_case(opponent.active outspeeds my.active)` — these are
  **estimates → tribool**, each wrapped in exactly one **resolver** (avoids E030), and it
  chose the *right* one: `worst_case` for the threat it's avoiding, `likely` for the KO it's
  pressing.
- `exists bench b where resists(...)` + `switch_to best bench by matchup_score(it, ...)` —
  correct quantifier and selector, with `it` used only inside the `by` binding.
- a mandatory `otherwise` closes **both** blocks, and `on forced_switch` stays **switch-only**.

The compiled IR is checked in too: [`hazard_keeper.policy.json`](./hazard_keeper.policy.json) —
the exact artifact the Python runtime interprets.

## Reproduce it

```bash
pip install -e "evalkit[agent]" -e evals   # deepagents + langchain + MCP adapters
export ANTHROPIC_API_KEY=sk-ant-...
# local Showdown on :8000 + a built riposte-c
evalkit run evals/features/hazard_control.feature --steps riposte_evals.steps \
  --driver deepagents --mcp-cmd riposte-mcp --model claude-opus-4-8 --condition mcp-repair
```

Numbers vary run to run (the agent's exploration and the battle RNG are not fixed).
