"""Per-scenario World shared across a scenario's steps.

Fresh per scenario. Steps read/write it: a `Given` sets the condition, a `When` calls the
driver and stashes the produced `Artifact`, `Then` steps assert against it. `data` is free
scratch for domain steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .driver import AgentDriver, Artifact, Condition


@dataclass
class World:
    driver: AgentDriver
    config: dict = field(default_factory=dict)
    brief: str = ""  # the Feature's description text
    condition: Condition = field(default_factory=lambda: Condition("default"))
    artifact: Optional[Artifact] = None
    data: dict[str, Any] = field(default_factory=dict)
