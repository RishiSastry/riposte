"""Gherkin step definitions for Riposte evals (step-level Given/When/Then mapping).

Registered with evalkit's global registry on import. `Then` steps are the concrete graded
checks: the program compiles, wins ≥P% of N battles vs a baseline, and stays within a quirk-
violation budget — the SPEC §7.3 metrics, expressed as natural-language scenario steps.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import subprocess
import tempfile
from pathlib import Path

from evalkit import Condition, then, when
from evalkit.registry import given

from .baselines import baseline_player

REPO_ROOT = Path(__file__).resolve().parents[2]
FORMAT = "gen9randombattle"
QUIRK_CODES = {"E020", "E030", "E031", "E032", "E040", "E041"}  # the steering-quirk diagnostics

# steering-condition presets (mirror evalkit.cli.CONDITIONS; SPEC §7.2 / D-4)
_CONDITIONS = {
    "mcp": Condition("mcp", allow_check_program=False, max_repair_rounds=0),
    "mcp-repair": Condition("mcp-repair", allow_check_program=True, max_repair_rounds=3),
}

_account_counter = itertools.count()


# ─────────────────────────────── compiler ───────────────────────────────


def _find_compiler() -> Path:
    if env := os.environ.get("RIPOSTE_C"):
        return Path(env)
    for build in ("release", "debug"):
        cand = REPO_ROOT / "compiler" / "target" / build / "riposte-c"
        if cand.exists():
            return cand
    raise FileNotFoundError("riposte-c not built. Run `cargo build` in compiler/ or set RIPOSTE_C.")


def _compile(source: str) -> tuple[dict, str | None]:
    """Compile source, returning (diag_report, policy_json_path_or_None)."""
    compiler = _find_compiler()
    tmp = Path(tempfile.mkdtemp(prefix="riposte-eval-"))
    src = tmp / "bot.rpo"
    src.write_text(source)
    subprocess.run([str(compiler), "build", str(src), "--out-dir", str(tmp)], capture_output=True)
    diag = json.loads((tmp / "bot.diag.json").read_text())
    policy = tmp / "bot.policy.json"
    return diag, (str(policy) if policy.exists() else None)


def _ensure_compiled(world) -> str:
    """Compile the current artifact once (cached on the world). Returns the policy path;
    fails the step if there's no program or it doesn't compile."""
    if "policy_path" in world.data:
        if world.data["policy_path"] is None:
            raise AssertionError("program did not compile; cannot evaluate")
        return world.data["policy_path"]
    assert world.artifact is not None, "no program written — is there a `When the agent writes...` step?"
    diag, policy = _compile(world.artifact.source)
    world.data["diagnostics"] = diag.get("diagnostics", [])
    world.data["policy_path"] = policy
    if policy is None:
        codes = ", ".join(d["code"] for d in world.data["diagnostics"])
        raise AssertionError(f"program did not compile ({codes})")
    return policy


# ──────────────────────────────── battles ───────────────────────────────


async def _play(policy_path: str, baseline: str, n: int) -> tuple[int, int]:
    from poke_env import AccountConfiguration, LocalhostServerConfiguration

    from riposte_rt.player import RipostePlayer

    tag = f"{os.getpid()}-{next(_account_counter)}"
    common = dict(
        battle_format=FORMAT,
        server_configuration=LocalhostServerConfiguration,
        max_concurrent_battles=10,
    )
    me = RipostePlayer.from_policy_file(
        policy_path, account_configuration=AccountConfiguration(f"rip-{tag}", None), **common
    )
    opp = baseline_player(baseline)(
        account_configuration=AccountConfiguration(f"opp-{tag}", None), **common
    )
    await me.battle_against(opp, n_battles=n)
    return me.n_won_battles, me.n_won_battles + opp.n_won_battles


# ─────────────────────────────── step defs ──────────────────────────────


@given(r'the steering condition "(?P<name>[\w-]+)"')
def _set_condition(world, name):
    if name not in _CONDITIONS:
        raise AssertionError(f"unknown steering condition '{name}'. Known: {', '.join(_CONDITIONS)}")
    world.condition = _CONDITIONS[name]


@given(r"baselines? (?P<names>[\w, ]+)")
def _declare_baselines(world, names):
    # validate + record; the win-rate step names its own baseline, so this just documents intent
    keys = [b.strip() for b in names.replace(" and ", ",").split(",") if b.strip()]
    for k in keys:
        baseline_player(k)  # raises on unknown
    world.data["baselines"] = keys


@when(r"the agent writes a Riposte bot")
async def _agent_writes(world):
    world.artifact = await world.driver.write_program(world.brief, world.condition)
    world.data.pop("policy_path", None)  # invalidate any cached compile


@then(r"the program compiles(?: without errors)?")
def _compiles(world):
    _ensure_compiled(world)  # raises AssertionError with the diagnostic codes on failure


@then(r"it wins >= (?P<pct>[\d.]+)% of (?P<n>\d+) battles vs (?P<baseline>\w+)")
async def _wins(world, pct, n, baseline):
    # compile off the event loop (blocking subprocess), then await the battles directly —
    # no nested event loop, so many win-rate steps run concurrently in one loop.
    policy_path = await asyncio.to_thread(_ensure_compiled, world)
    n = int(n)
    # CI / smoke override: cap battles so test runs stay fast without editing the feature
    # (the feature declares the real N for a full experiment run).
    if cap := os.environ.get("RIPOSTE_EVAL_MAX_BATTLES"):
        n = min(n, int(cap))
    threshold = float(pct) / 100.0
    won, total = await _play(policy_path, baseline, n)
    rate = won / total if total else 0.0
    assert rate >= threshold, (
        f"win rate {rate:.0%} ({won}/{total}) vs {baseline} < required {threshold:.0%}"
    )


@then(r"it makes <= (?P<k>\d+) quirk violations?")
def _quirk_budget(world, k):
    # Count quirk-code diagnostics from compiling the produced program.
    _compile_diag = world.data.get("diagnostics")
    if _compile_diag is None:
        try:
            _ensure_compiled(world)
        except AssertionError:
            pass  # a non-compiling program still has diagnostics to count
        _compile_diag = world.data.get("diagnostics", [])
    violations = [d for d in _compile_diag if d["code"] in QUIRK_CODES]
    assert len(violations) <= int(k), (
        f"{len(violations)} quirk violation(s) > budget {k}: "
        + ", ".join(d["code"] for d in violations)
    )
