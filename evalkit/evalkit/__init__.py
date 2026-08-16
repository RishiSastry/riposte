"""evalkit — generic agent-steering eval framework.

Runs Gherkin `.feature` evals against a deep agent wired to an MCP server. Domain-agnostic:
domain packages register step definitions and provide an `AgentDriver`; nothing here imports
any specific domain (e.g. Riposte).
"""

from .driver import AgentDriver, Artifact, Condition, StubDriver
from .registry import StepRegistry, given, registry, step, then, when
from .result import RunResult, ScenarioResult, Status, StepResult
from .world import World

__version__ = "0.1.0"

__all__ = [
    "AgentDriver",
    "Artifact",
    "Condition",
    "StubDriver",
    "StepRegistry",
    "registry",
    "given",
    "when",
    "then",
    "step",
    "World",
    "RunResult",
    "ScenarioResult",
    "Status",
    "StepResult",
    "__version__",
]
