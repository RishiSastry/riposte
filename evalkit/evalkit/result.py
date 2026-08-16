"""Result model for a Gherkin eval run."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    UNDEFINED = "undefined"  # no step definition matched
    ERROR = "error"  # step raised a non-assertion exception


@dataclass
class StepResult:
    keyword: str  # "Given ", "When ", "Then ", "And "
    text: str
    status: Status
    message: str = ""
    duration_s: float = 0.0


@dataclass
class ScenarioResult:
    feature: str
    name: str
    steps: list[StepResult] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def status(self) -> Status:
        bad = {Status.FAILED, Status.ERROR, Status.UNDEFINED}
        for s in self.steps:
            if s.status in bad:
                return s.status
        return Status.PASSED

    @property
    def passed(self) -> bool:
        return self.status == Status.PASSED


@dataclass
class RunResult:
    scenarios: list[ScenarioResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.scenarios)

    @property
    def passed(self) -> int:
        return sum(1 for s in self.scenarios if s.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def ok(self) -> bool:
        return self.failed == 0
