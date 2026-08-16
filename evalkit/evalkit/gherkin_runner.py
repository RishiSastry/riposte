"""Custom Gherkin runner: parse .feature files with the official gherkin parser, then
execute scenarios against a StepRegistry ourselves (so grading/reporting are fully ours).

Mapping (SPEC §7.1, step-level): the Feature's description is the natural-language brief; each
Scenario is a set of Given/When/Then steps; `Then` steps are concrete graded checks.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from gherkin.parser import Parser
from gherkin.token_scanner import TokenScanner

from .registry import AmbiguousStep, NoMatch, StepRegistry
from .result import ScenarioResult, Status, StepResult
from .world import World

DEFAULT_PARALLELISM = 4


@dataclass
class Step:
    keyword: str
    text: str


@dataclass
class Scenario:
    name: str
    steps: list[Step]
    tags: list[str] = field(default_factory=list)


@dataclass
class Feature:
    name: str
    description: str  # the brief
    background: list[Step]
    scenarios: list[Scenario]
    tags: list[str] = field(default_factory=list)
    path: str = ""


def parse_feature(path: str | Path) -> Feature:
    text = Path(path).read_text()
    doc = Parser().parse(TokenScanner(text))
    feat = doc["feature"]
    background: list[Step] = []
    scenarios: list[Scenario] = []
    for child in feat.get("children", []):
        if "background" in child:
            background = _steps(child["background"])
        elif "scenario" in child:
            sc = child["scenario"]
            scenarios.append(
                Scenario(name=sc["name"], steps=_steps(sc), tags=_tags(sc))
            )
    return Feature(
        name=feat["name"],
        description=(feat.get("description") or "").strip(),
        background=background,
        scenarios=scenarios,
        tags=_tags(feat),
        path=str(path),
    )


def _steps(node: dict) -> list[Step]:
    return [Step(keyword=s["keyword"], text=s["text"]) for s in node.get("steps", [])]


def _tags(node: dict) -> list[str]:
    return [t["name"] for t in node.get("tags", [])]


# ─────────────────────────────── execution ──────────────────────────────
# Async-first: all scenarios across all features run in ONE event loop, concurrently under a
# shared semaphore. A step function may be `async def` (awaited directly — e.g. battles, LLM
# calls) or a plain `def` (offloaded to a worker thread so a blocking call like a subprocess
# doesn't stall the other concurrent scenarios).


async def run_features_async(
    paths: list[str | Path],
    registry: StepRegistry,
    world_factory: Callable[[], World],
    *,
    parallelism: int = DEFAULT_PARALLELISM,
) -> list[ScenarioResult]:
    """Run every scenario across every feature concurrently, bounded by `parallelism`."""
    sem = asyncio.Semaphore(parallelism)
    feature_results = await asyncio.gather(
        *(run_feature_async(p, registry, world_factory, sem=sem) for p in paths)
    )
    return [r for feat in feature_results for r in feat]


async def run_feature_async(
    path: str | Path,
    registry: StepRegistry,
    world_factory: Callable[[], World],
    *,
    parallelism: int = DEFAULT_PARALLELISM,
    sem: asyncio.Semaphore | None = None,
) -> list[ScenarioResult]:
    feature = parse_feature(path)
    sem = sem or asyncio.Semaphore(parallelism)

    async def one(scenario: Scenario) -> ScenarioResult:
        async with sem:
            world = world_factory()
            world.brief = feature.description
            return await _run_scenario(feature, scenario, feature.background, registry, world)

    return list(await asyncio.gather(*(one(s) for s in feature.scenarios)))


def run_feature(
    path: str | Path,
    registry: StepRegistry,
    world_factory: Callable[[], World],
) -> list[ScenarioResult]:
    """Synchronous convenience wrapper (one scenario at a time). Tests and simple callers use
    this; the CLI uses `run_features_async` for real parallelism."""
    return asyncio.run(run_feature_async(path, registry, world_factory, parallelism=1))


async def _run_scenario(
    feature: Feature,
    scenario: Scenario,
    background: list[Step],
    registry: StepRegistry,
    world: World,
) -> ScenarioResult:
    result = ScenarioResult(feature=feature.name, name=scenario.name, tags=scenario.tags)
    failed = False
    for step in [*background, *scenario.steps]:
        if failed:
            result.steps.append(StepResult(step.keyword, step.text, Status.SKIPPED))
            continue
        sr = await _run_step(step, registry, world)
        result.steps.append(sr)
        if sr.status in (Status.FAILED, Status.ERROR, Status.UNDEFINED):
            failed = True
    return result


async def _run_step(step: Step, registry: StepRegistry, world: World) -> StepResult:
    start = time.monotonic()
    try:
        func, args, kwargs = registry.resolve(step.text)
    except NoMatch:
        return StepResult(step.keyword, step.text, Status.UNDEFINED, "no step definition")
    except AmbiguousStep as e:
        return StepResult(step.keyword, step.text, Status.ERROR, str(e))
    try:
        if inspect.iscoroutinefunction(func):
            await func(world, *args, **kwargs)
        else:
            # offload blocking sync steps so concurrent scenarios keep progressing
            await asyncio.to_thread(func, world, *args, **kwargs)
        return StepResult(step.keyword, step.text, Status.PASSED, duration_s=_since(start))
    except AssertionError as e:
        return StepResult(step.keyword, step.text, Status.FAILED, str(e) or "assertion failed", _since(start))
    except Exception as e:  # noqa: BLE001 — surface any step crash as ERROR
        return StepResult(step.keyword, step.text, Status.ERROR, f"{type(e).__name__}: {e}", _since(start))


def _since(start: float) -> float:
    return round(time.monotonic() - start, 3)
