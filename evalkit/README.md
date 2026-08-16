# evalkit — generic agent-steering eval framework

Domain-agnostic. Runs **Gherkin `.feature` evals** against a **deep agent wired to an MCP
server**, and grades what the agent writes. Parameterized by (a) an MCP server executable and
(b) domain step definitions — **no Riposte or Pokémon imports live here** (that boundary is
what keeps it reusable; Riposte's bindings are in [`../evals/`](../evals/)).

## Pieces

| Module              | Role                                                                    |
|---------------------|-------------------------------------------------------------------------|
| `gherkin_runner.py` | Parse `.feature` (official gherkin lib) + execute scenarios ourselves.  |
| `registry.py`       | Step-definition registry + `given`/`when`/`then` decorators (the extensibility surface). |
| `world.py`          | Per-scenario `World` shared across a scenario's steps.                  |
| `driver.py`         | `AgentDriver` protocol, `Condition` (steering variable), `Artifact`, `StubDriver`. |
| `deepagents_driver.py` | `DeepAgentsDriver`: LangChain `deepagents` + MCP tools (Claude). Lazy heavy deps. |
| `report.py`         | Console + JUnit XML + JSON reporters.                                   |
| `cli.py`            | `evalkit run` — the CI entrypoint.                                       |

## Mapping: a scenario → a graded eval (SPEC §7.1, step-level)

The Feature's **description is the natural-language brief**; each Scenario is Given/When/Then;
`Then` steps are concrete checks. Domain packages supply the step meanings.

```gherkin
Feature: Hazard control
  Write a bot that keeps hazards up and pivots out of bad matchups.

  Scenario: Competitive under MCP+repair
    Given the steering condition "mcp-repair"
    When the agent writes a Riposte bot
    Then the program compiles without errors
    And it wins >= 60% of 50 battles vs random
    And it makes <= 0 quirk violations
```

## Install & run (CI build tool)

```bash
pip install -e evalkit            # core (gherkin + runner + stub driver + CLI)
pip install -e "evalkit[agent]"   # + deepagents / langchain / MCP adapters for the real driver

# a build/CI stage runs the evals:
evalkit run evals/features/ \
  --steps riposte_evals.steps \
  --driver deepagents --mcp-cmd "riposte-mcp" --model claude-opus-4-8 \
  --condition mcp-repair --parallel 8 --junit out.xml
# exits non-zero if any scenario fails, so the build gates on it.
```

## Parallelism

Execution is **async, single-event-loop**: every scenario across every feature runs
concurrently under one semaphore (`--parallel N`, default 4). A step may be `async def`
(awaited directly — LLM calls, battles) or plain `def` (offloaded to a thread so a blocking
subprocess doesn't stall the other scenarios). One loop is also a correctness property — the
per-scenario `asyncio.run()` an earlier design used stranded poke-env's websocket state
across loops and deadlocked; there is exactly one loop now.

Dry-run the pipeline without an LLM: `--driver stub --stub-source examples/hazard_control.rpo`.

## Extensibility

- **Steps:** `--steps <module>` imports domain step modules; each registers step patterns via
  the `@given/@when/@then` decorators bound to the global `registry`.
- **Drivers:** implement the `AgentDriver` protocol (`write_program(brief, condition) -> Artifact`).
- **Conditions:** the steering variable (`Condition`) gates MCP tool exposure and repair rounds.
