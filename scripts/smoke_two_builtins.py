"""M0 smoke test: two built-in poke-env players complete battles headlessly
against the local Showdown server. Validates the poke-env <-> local-server plumbing
before any Riposte code exists.

Usage (from repo root, runtime venv active):
    python evals/smoke_two_builtins.py --n 20

Requires the local Showdown server running with --no-security on :8000.
"""

from __future__ import annotations

import argparse
import asyncio

from poke_env import AccountConfiguration, LocalhostServerConfiguration
from poke_env.player import MaxBasePowerPlayer, RandomPlayer

FORMAT = "gen9randombattle"


async def run(n: int) -> tuple[int, int]:
    rand = RandomPlayer(
        account_configuration=AccountConfiguration("smoke-rand", None),
        battle_format=FORMAT,
        server_configuration=LocalhostServerConfiguration,
        max_concurrent_battles=10,
    )
    maxbp = MaxBasePowerPlayer(
        account_configuration=AccountConfiguration("smoke-maxbp", None),
        battle_format=FORMAT,
        server_configuration=LocalhostServerConfiguration,
        max_concurrent_battles=10,
    )
    await rand.battle_against(maxbp, n_battles=n)
    return maxbp.n_won_battles, rand.n_won_battles


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20, help="number of battles")
    args = ap.parse_args()

    maxbp_wins, rand_wins = asyncio.run(run(args.n))
    total = maxbp_wins + rand_wins
    rate = maxbp_wins / total if total else 0.0
    print(f"battles completed: {total}/{args.n}")
    print(f"MaxBasePowerPlayer wins: {maxbp_wins}  ({rate:.0%})")
    print(f"RandomPlayer wins:       {rand_wins}")
    # sanity: MaxBasePower should dominate Random
    assert total == args.n, f"only {total}/{args.n} battles finished — plumbing issue"
    print("OK: plumbing works, battles complete headlessly.")


if __name__ == "__main__":
    main()
