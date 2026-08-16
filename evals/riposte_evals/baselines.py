"""Baseline opponents (SPEC §7.3). Names used in `.feature` files map to poke-env players."""

from __future__ import annotations

from poke_env.player import MaxBasePowerPlayer, RandomPlayer, SimpleHeuristicsPlayer

BASELINES = {
    "random": RandomPlayer,
    "maxbp": MaxBasePowerPlayer,
    "max": MaxBasePowerPlayer,
    "heuristics": SimpleHeuristicsPlayer,
    "heur": SimpleHeuristicsPlayer,
    "simpleheuristics": SimpleHeuristicsPlayer,
}


def baseline_player(name: str):
    key = name.strip().lower()
    if key not in BASELINES:
        raise KeyError(f"unknown baseline '{name}'. Known: {', '.join(sorted(set(BASELINES)))}")
    return BASELINES[key]
