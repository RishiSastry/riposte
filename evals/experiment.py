"""Steering-delivery experiment (SPEC §7): tasks × conditions × models × k, run concurrently
in one event loop, graded by the SPEC §7.3 metrics — compile pass, quirk-error frequency,
win rate vs a baseline, repair rounds, tool calls, tokens.

Usage (needs evalkit[agent] + ANTHROPIC_API_KEY + local Showdown + built riposte-c):
    python evals/experiment.py                       # default bounded matrix
    python evals/experiment.py --models claude-opus-4-8 --k 2 --n 60

Writes evals/results/<timestamp>.json and prints a markdown summary.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
from pathlib import Path

from evalkit.deepagents_driver import DeepAgentsDriver
from evalkit.driver import CONDITIONS

from riposte_evals.baselines import baseline_player  # noqa: F401 (validates baseline names)
from riposte_evals.steering import steering_docs
from riposte_evals.steps import QUIRK_CODES, _compile, _play

REPO = Path(__file__).resolve().parent
RESULTS = REPO / "results"

# Task set (brief = the natural-language spec; graded vs `baseline`).
TASKS = [
    {
        "id": "hazard_control",
        "brief": (
            "Write a Riposte bot that keeps entry hazards up — set Stealth Rock when your active "
            "mon knows it and the opponent's side doesn't already have it — pivots out of bad "
            "matchups when the opponent is faster and likely to KO you, and presses the attack "
            "when you have a clear KO."
        ),
    },
    {
        "id": "hyper_offense",
        "brief": (
            "Write a Riposte bot that plays hyper-offense: terastallize early to secure a KO when "
            "one is likely and tera is available, otherwise press the strongest attack whenever "
            "you can KO, and pivot to a bench mon that can likely KO the opponent when outsped."
        ),
    },
    {
        "id": "type_matchup_pivot",
        "brief": (
            "Write a Riposte bot that plays the type-matchup game: if the opponent's primary type "
            "is super-effective against your active mon, switch to a bench mon that resists it; "
            "otherwise attack with your strongest move. When forced to switch, pick a resister if "
            "one exists, else the healthiest mon."
        ),
    },
]


async def run_cell(task, cond, model, sample, docs, sem, n, baseline):
    async with sem:
        cell = {
            "task": task["id"],
            "condition": cond.name,
            "model": model,
            "sample": sample,
        }
        try:
            driver = DeepAgentsDriver(mcp_cmd=["riposte-mcp"], model=model, docs=docs)
            art = await driver.write_program(task["brief"], cond)
            diag, policy = await asyncio.to_thread(_compile, art.source)
            quirk_errs = [d["code"] for d in diag["diagnostics"] if d["code"] in QUIRK_CODES]
            cell.update(
                compiled=policy is not None,
                n_diagnostics=len(diag["diagnostics"]),
                quirk_errors=quirk_errs,
                repair_rounds=art.repair_rounds,
                tokens=art.tokens,
                source=art.source,
            )
            if policy is not None:
                won, total = await _play(policy, baseline, n)
                cell.update(won=won, total=total, win_rate=(won / total if total else None))
            else:
                cell.update(won=0, total=0, win_rate=None)
        except Exception as e:  # noqa: BLE001 — one cell failing shouldn't kill the matrix
            cell["error"] = f"{type(e).__name__}: {e}"
        print(
            f"  done: {cell['task']:<20} {cell['condition']:<14} {model:<18} "
            f"compiled={cell.get('compiled')} win={cell.get('win_rate')}"
        )
        return cell


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 3) if xs else None


def _wilson(k, n, z=1.96):
    """Wilson 95% score interval for k/n. Returns (p, lo, hi) as fractions."""
    if not n:
        return None, None, None
    p = k / n
    d = 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, center - half), min(1.0, center + half)


def _pct_ci(k, n):
    p, lo, hi = _wilson(k, n)
    return "—" if p is None else f"{p:.0%} [{lo:.0%}–{hi:.0%}]"


def _metrics(cc) -> str:
    """The four metric cells (no label): compile-pass | quirk | win-rate | tokens."""
    passed = sum(1 for c in cc if c.get("compiled"))
    quirk = _avg([len(c.get("quirk_errors", [])) for c in cc])
    won = sum(c.get("won", 0) for c in cc if c.get("compiled"))
    tot = sum(c.get("total", 0) for c in cc if c.get("compiled"))
    toks = _avg([c.get("tokens") for c in cc])
    return f"{_pct_ci(passed, len(cc))} | {quirk} | {_pct_ci(won, tot)} | {toks:.0f}"


def summarize(cells) -> str:
    cells = [c for c in cells if "error" not in c]
    conds = sorted({c["condition"] for c in cells})
    models = sorted({c["model"] for c in cells})

    out = ["## By condition (pooled over tasks + models)", "",
           "| condition | compile-pass [95% CI] | avg quirk-errs | win-rate [95% CI] | avg tokens |",
           "|---|---|---|---|---|"]
    for cond in conds:
        out.append(f"| {cond} | {_metrics([c for c in cells if c['condition'] == cond])} |")

    out += ["", "## By condition × model", "",
            "| condition | model | compile-pass [95% CI] | avg quirk-errs | win-rate [95% CI] | avg tokens |",
            "|---|---|---|---|---|---|"]
    for cond in conds:
        for m in models:
            cc = [c for c in cells if c["condition"] == cond and c["model"] == m]
            if cc:
                out.append(f"| {cond} | {m} | {_metrics(cc)} |")
    out.append("\nWin-rate is pooled over all battles of compiled programs (Wilson 95% CI); "
               "compile-pass CI is over cells. Per-cell detail (tool calls, repair rounds, "
               "source) in the JSON.")
    return "\n".join(out)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", nargs="+", default=None, help="task ids to run (default: all)")
    ap.add_argument("--conditions", nargs="+", default=["C1-docs", "C2-mcp", "C4-mcp-repair"])
    ap.add_argument("--models", nargs="+", default=["claude-opus-4-8", "claude-haiku-4-5"])
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--n", type=int, default=40, help="battles per cell vs baseline")
    ap.add_argument("--baseline", default="heuristics")
    ap.add_argument("--parallel", type=int, default=4)
    args = ap.parse_args()

    docs = steering_docs()
    conds = [CONDITIONS[c] for c in args.conditions]
    tasks = [t for t in TASKS if args.tasks is None or t["id"] in args.tasks]
    cells_spec = [
        (t, c, m, s)
        for t in tasks
        for c in conds
        for m in args.models
        for s in range(args.k)
    ]
    print(
        f"matrix: {len(tasks)} tasks × {len(conds)} conditions × {len(args.models)} models × "
        f"k={args.k} = {len(cells_spec)} cells | baseline={args.baseline} N={args.n} | "
        f"docs={len(docs)//4}~tok"
    )
    sem = asyncio.Semaphore(args.parallel)
    t0 = time.time()
    cells = await asyncio.gather(
        *(run_cell(t, c, m, s, docs, sem, args.n, args.baseline) for (t, c, m, s) in cells_spec)
    )
    elapsed = round(time.time() - t0)

    RESULTS.mkdir(exist_ok=True)
    stamp = int(t0)
    out = RESULTS / f"{stamp}.json"
    out.write_text(json.dumps({"args": vars(args), "seconds": elapsed, "cells": cells}, indent=2))
    table = summarize(cells)
    (RESULTS / f"{stamp}.md").write_text(f"# Results ({stamp}, {elapsed}s)\n\n{table}\n")
    print(f"\n=== SUMMARY (by condition) — {elapsed}s ===\n{table}\n\nwrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
