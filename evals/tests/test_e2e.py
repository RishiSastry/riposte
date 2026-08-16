"""End-to-end eval-framework test with the deterministic StubDriver standing in for the
agent: parse .feature → produce a golden program → compile with riposte-c → play battles →
check the quirk budget. Proves the whole pipeline without spending LLM tokens.

Skipped unless a local Showdown server is on :8000 and riposte-c is built — those are the
same prerequisites a real eval run needs.
"""

import os
import socket
from pathlib import Path

import pytest

# Keep the integration test snappy: cap battles per win-rate step. The .feature files still
# declare the real N for a full experiment run; this only bounds the golden-stub smoke.
os.environ.setdefault("RIPOSTE_EVAL_MAX_BATTLES", "10")

import asyncio

import riposte_evals.steps  # noqa: F401 — registers the step definitions
from evalkit import Condition, StubDriver, World
from evalkit.gherkin_runner import run_features_async
from evalkit.registry import registry

REPO = Path(__file__).resolve().parents[2]


def _server_up() -> bool:
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(("localhost", 8000))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _compiler_built() -> bool:
    if os.environ.get("RIPOSTE_C"):
        return True
    return any((REPO / "compiler" / "target" / b / "riposte-c").exists() for b in ("release", "debug"))


pytestmark = pytest.mark.skipif(
    not (_server_up() and _compiler_built()),
    reason="needs a local Showdown server on :8000 and a built riposte-c",
)


def _golden_driver() -> StubDriver:
    hazard = (REPO / "examples" / "hazard_control.rpo").read_text()
    offense = (REPO / "examples" / "hyper_offense.rpo").read_text()
    return StubDriver(by_brief={"hazard": hazard, "offense": offense}, default=hazard)


def test_all_features_pass_with_golden_program():
    """Both features run concurrently in ONE event loop (the parallel path). The golden
    program stands in for the agent; every scenario should compile, beat random, and stay
    within the quirk budget."""
    driver = _golden_driver()
    features = [
        REPO / "evals" / "features" / "hazard_control.feature",
        REPO / "evals" / "features" / "hyper_offense.feature",
    ]

    def world_factory() -> World:
        return World(
            driver=driver,
            condition=Condition("mcp-repair", allow_check_program=True, max_repair_rounds=3),
        )

    results = asyncio.run(
        run_features_async(features, registry, world_factory, parallelism=2)
    )
    assert results, "no scenarios ran"
    for r in results:
        detail = "; ".join(
            f"{s.text} [{s.status.value}]" + (f" — {s.message}" if s.message else "")
            for s in r.steps
        )
        assert r.passed, f"scenario '{r.name}' failed: {detail}"
