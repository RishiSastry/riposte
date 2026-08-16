"""RipostePlayer: a poke-env Player that plays according to a compiled policy IR.

Per SPEC §6: build the state surface from the Battle, pick the block (turn vs
forced_switch), evaluate rules top-down, apply fallback semantics, and emit a per-turn
JSONL trace (the trajectory data for evals and the blog post).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from poke_env.battle import Battle
from poke_env.player import Player

from . import interp
from .ir import Policy, Rule


class RipostePlayer(Player):
    def __init__(self, policy: Policy, *args: Any, trace_path: Optional[str] = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._policy = policy
        self._trace_path = Path(trace_path) if trace_path else None
        self.fallback_count = 0
        self.decision_count = 0

    @classmethod
    def from_policy_file(cls, path: str, *args: Any, **kwargs: Any) -> "RipostePlayer":
        return cls(Policy.load(path), *args, **kwargs)

    def choose_move(self, battle: Battle) -> Any:  # type: ignore[override]
        forced = bool(getattr(battle, "force_switch", False))
        rules = self._policy.on_forced_switch if forced else self._policy.on_turn
        ctx = interp.Ctx(battle)

        fired: Optional[str] = None
        fallback = False
        order = None
        for rule in rules:
            if not self._when_true(rule, ctx):
                continue
            candidate = interp.execute_action(rule.action, ctx, self)
            if candidate is not None:
                fired, order = rule.rule_name, candidate
                break
            # action illegal right now → fall through to the next rule (SPEC §4.1)

        if order is None:
            # otherwise was also illegal / no rule produced a legal action
            fallback = True
            self.fallback_count += 1
            order = self.choose_random_move(battle)

        self.decision_count += 1
        self._trace(battle, forced, fired, fallback, order)
        return order

    def _when_true(self, rule: Rule, ctx: interp.Ctx) -> bool:
        if rule.when is None:  # otherwise
            return True
        return interp._as_bool(interp.eval_expr(rule.when, ctx))

    def _trace(self, battle: Battle, forced: bool, fired: Optional[str], fallback: bool, order: Any) -> None:
        if self._trace_path is None:
            return
        rec = {
            "battle": battle.battle_tag,
            "turn": battle.turn,
            "block": "forced_switch" if forced else "turn",
            "fired_rule": fired,
            "runtime_fallback": fallback,
            "action": str(order),
        }
        with self._trace_path.open("a") as f:
            f.write(json.dumps(rec) + "\n")
