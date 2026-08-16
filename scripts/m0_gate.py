"""M0 exit gate (SPEC §9): a hand-written policy.json, interpreted by RipostePlayer, must
beat RandomPlayer >70% over 100 battles. Also reports the runtime-fallback rate (proxy for
legality-reasoning quality) and, for reference, MaxBasePower and SimpleHeuristics.

Usage (repo root, runtime venv active, Showdown running on :8000):
    python evals/m0_gate.py --n 100
    python evals/m0_gate.py --n 100 --opponent max     # vs MaxBasePowerPlayer
    python evals/m0_gate.py --n 100 --opponent heur     # vs SimpleHeuristicsPlayer
"""

from __future__ import annotations

import argparse
import asyncio

from poke_env import AccountConfiguration, LocalhostServerConfiguration
from poke_env.player import MaxBasePowerPlayer, RandomPlayer, SimpleHeuristicsPlayer

from riposte_rt.player import RipostePlayer

FORMAT = "gen9randombattle"
POLICY = "examples/m0_skeleton.policy.json"

OPPONENTS = {"random": RandomPlayer, "max": MaxBasePowerPlayer, "heur": SimpleHeuristicsPlayer}


async def run(n: int, opp_key: str, trace: str | None) -> tuple[int, int, int, int]:
    common = dict(
        battle_format=FORMAT,
        server_configuration=LocalhostServerConfiguration,
        max_concurrent_battles=10,
    )
    riposte = RipostePlayer.from_policy_file(
        POLICY,
        account_configuration=AccountConfiguration("riposte-m0", None),
        trace_path=trace,
        **common,
    )
    opp = OPPONENTS[opp_key](
        account_configuration=AccountConfiguration(f"opp-{opp_key}", None),
        **common,
    )
    await riposte.battle_against(opp, n_battles=n)
    return riposte.n_won_battles, opp.n_won_battles, riposte.fallback_count, riposte.decision_count


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--opponent", choices=list(OPPONENTS), default="random")
    ap.add_argument("--trace", default=None, help="optional JSONL trace path")
    args = ap.parse_args()

    won, lost, fb, decisions = asyncio.run(run(args.n, args.opponent, args.trace))
    total = won + lost
    wr = won / total if total else 0.0
    fb_rate = fb / decisions if decisions else 0.0
    print(f"opponent:            {args.opponent}")
    print(f"battles:             {total}/{args.n}")
    print(f"Riposte win rate:    {won}/{total} = {wr:.1%}")
    print(f"runtime fallbacks:   {fb}/{decisions} decisions = {fb_rate:.2%}")
    if args.opponent == "random":
        gate = "PASS ✅" if wr > 0.70 else "FAIL ❌"
        print(f"M0 gate (>70% vs random): {gate}")


if __name__ == "__main__":
    main()
