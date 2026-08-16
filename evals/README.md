# evals — Riposte-specific eval bindings

The concrete experiment for Riposte. Depends on the generic [`../evalkit/`](../evalkit/) and
supplies everything Pokémon/Riposte-specific: Gherkin step definitions, baseline opponents,
and the `.feature` task briefs. See [SPEC.md §7](../SPEC.md).

## Layout

| Path                       | What lives here                                                    |
|----------------------------|-------------------------------------------------------------------|
| `riposte_evals/steps.py`   | Step definitions: *agent writes a bot* (driver) · *compiles* (riposte-c) · *wins ≥P% of N vs baseline* (RipostePlayer) · *≤K quirk violations* (diag codes). |
| `riposte_evals/baselines.py` | Baseline name → poke-env player (`random`, `maxbp`, `heuristics`). |
| `features/*.feature`       | Task briefs as Gherkin (the feature description is the brief).     |
| `tests/test_e2e.py`        | Full pipeline with the golden program as a stand-in agent.        |
| `tasks/ golden/ conditions/ analysis/` | Room for more briefs, golden `.rpo`, condition configs, notebooks. |

## Run

Prereqs: a local Showdown server on `:8000` (`node pokemon-showdown start --no-security`) and
a built compiler (`cargo build` in `compiler/`).

```bash
pip install -e evalkit -e evals        # riposte_evals depends on evalkit + riposte-rt

# real run (needs an Anthropic credential + evalkit[agent]):
evalkit run evals/features/ --steps riposte_evals.steps \
  --driver deepagents --mcp-cmd riposte-mcp --condition mcp-repair

# dry run with the golden program instead of an agent:
evalkit run evals/features/hazard_control.feature --steps riposte_evals.steps \
  --driver stub --stub-source examples/hazard_control.rpo
```

## The headline metric (future)

`steps.py` grades win rate vs fixed baselines. The **"compiles but loses" gap** — agent
program win rate vs the *golden* program on the same task — is the semantic-quality signal the
SPEC calls out (§7.3.4); a `golden` baseline that plays a reference `.rpo` slots into the same
win-rate step.
