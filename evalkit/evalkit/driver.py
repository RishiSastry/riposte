"""Agent-driver interface. The framework is parameterized by an MCP server executable and a
driver that turns a natural-language brief into a program (the artifact under test).

`AgentDriver` is generic — the "program" is just text — so evalkit stays domain-agnostic.
`DeepAgentsDriver` (in deepagents_driver.py) is the real implementation; `StubDriver` returns
a canned artifact for deterministic tests and dry runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Condition:
    """A steering condition — the experiment's independent variable (SPEC §7.2).

    - `name`: label, e.g. "mcp", "mcp-repair".
    - `allow_check_program`: expose the MCP `check_program` tool (D-4 default: repair only).
    - `max_repair_rounds`: how many diag-feedback repair rounds the agent may take.
    """

    name: str
    allow_check_program: bool = False
    max_repair_rounds: int = 0


@dataclass
class Artifact:
    """What the agent produced, plus telemetry for metrics (cost, repair efficiency)."""

    source: str
    repair_rounds: int = 0
    tokens: int = 0
    transcript: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@runtime_checkable
class AgentDriver(Protocol):
    async def write_program(self, brief: str, condition: Condition) -> Artifact:
        """Run the agent on `brief` under `condition` and return the program it wrote.

        Async so many scenarios' agents (and their battles) run concurrently in ONE event
        loop — the runner never spins up a second loop per scenario."""
        ...


class StubDriver:
    """Deterministic driver for tests/dry-runs. Returns a canned source, chosen by a
    substring match against the brief (first hit) or a default."""

    def __init__(self, by_brief: dict[str, str] | None = None, default: str = ""):
        self._by_brief = by_brief or {}
        self._default = default

    async def write_program(self, brief: str, condition: Condition) -> Artifact:
        for needle, source in self._by_brief.items():
            if needle.lower() in brief.lower():
                return Artifact(source=source, meta={"driver": "stub", "matched": needle})
        return Artifact(source=self._default, meta={"driver": "stub", "matched": None})
