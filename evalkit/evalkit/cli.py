"""`evalkit run` — the CI build entrypoint.

    evalkit run FEATURES...
        --steps riposte_evals.steps       # import domain step modules (register steps)
        --driver deepagents|stub          # how the agent writes programs
        --mcp-cmd "riposte-mcp"           # MCP server executable (deepagents driver)
        --model claude-opus-4-8           # driver model
        --condition mcp-repair            # steering condition preset
        --stub-source bot.rpo             # canned source for --driver stub (dry runs / CI)
        --junit out.xml  --json out.json  # machine-readable reports

Exits non-zero if any scenario fails, so a build stage can gate on it.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import shlex
import sys
from pathlib import Path

from . import report
from .driver import Condition, StubDriver
from .gherkin_runner import DEFAULT_PARALLELISM, run_features_async
from .registry import registry
from .result import RunResult
from .world import World

# Steering-condition presets (SPEC §7.2 / D-4). Override with --allow-check-program /
# --repair-rounds.
CONDITIONS = {
    "mcp": Condition("mcp", allow_check_program=False, max_repair_rounds=0),
    "mcp-repair": Condition("mcp-repair", allow_check_program=True, max_repair_rounds=3),
}


def _discover_features(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            out.extend(sorted(path.rglob("*.feature")))
        else:
            out.append(path)
    return out


def _build_driver(args) -> object:
    if args.driver == "stub":
        source = Path(args.stub_source).read_text() if args.stub_source else ""
        return StubDriver(default=source)
    if args.driver == "deepagents":
        from .deepagents_driver import DeepAgentsDriver  # lazy: heavy deps

        return DeepAgentsDriver(
            mcp_cmd=shlex.split(args.mcp_cmd) if args.mcp_cmd else None,
            model=args.model,
        )
    raise SystemExit(f"unknown driver: {args.driver}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evalkit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run .feature evals")
    run.add_argument("features", nargs="+", help=".feature files or directories")
    run.add_argument("--steps", action="append", default=[], help="step module(s) to import")
    run.add_argument("--driver", choices=["deepagents", "stub"], default="deepagents")
    run.add_argument("--mcp-cmd", default=None, help="MCP server executable (deepagents)")
    run.add_argument("--model", default="claude-opus-4-8", help="driver model")
    run.add_argument("--condition", default="mcp-repair", choices=list(CONDITIONS))
    run.add_argument("--allow-check-program", action="store_true")
    run.add_argument("--repair-rounds", type=int, default=None)
    run.add_argument("--stub-source", default=None, help="canned .rpo for --driver stub")
    run.add_argument(
        "--parallel",
        type=int,
        default=DEFAULT_PARALLELISM,
        help="max scenarios to run concurrently (one shared event loop)",
    )
    run.add_argument("--junit", default=None)
    run.add_argument("--json", default=None)
    args = ap.parse_args(argv)

    # extensibility: import domain step modules so they register their steps
    for mod in args.steps:
        importlib.import_module(mod)

    condition = CONDITIONS[args.condition]
    if args.allow_check_program:
        condition = Condition(condition.name, True, condition.max_repair_rounds)
    if args.repair_rounds is not None:
        condition = Condition(condition.name, condition.allow_check_program, args.repair_rounds)

    driver = _build_driver(args)
    config = {"model": args.model, "mcp_cmd": args.mcp_cmd}

    def world_factory() -> World:
        return World(driver=driver, config=config, condition=condition)

    paths = _discover_features(args.features)
    scenarios = asyncio.run(
        run_features_async(paths, registry, world_factory, parallelism=args.parallel)
    )
    run_result = RunResult(scenarios=scenarios)

    print(report.console(run_result))
    if args.junit:
        report.write_junit(run_result, args.junit)
    if args.json:
        report.write_json(run_result, args.json)
    return 0 if run_result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
