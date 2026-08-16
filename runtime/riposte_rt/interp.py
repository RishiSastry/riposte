"""IR interpreter: evaluate a condition expression tree and execute actions against a
poke-env Battle. Pure per decision (SPEC §6): same battle state → same action.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from poke_env.battle import Battle, Move, Pokemon

from . import ir
from . import predicates as P
from .predicates import Tri

# Pokemon field accessors reachable via a Ref path (SPEC §4.3). Kept explicit so an
# unknown field is a loud KeyError, not a silent None.
_MON_FIELDS = {
    "hp_fraction": lambda m: m.current_hp_fraction,
    "primary_type": lambda m: m.type_1,
    "types": lambda m: [t for t in (m.type_1, m.type_2) if t is not None],
    "species": lambda m: m.species,
    "status": lambda m: m.status,
    "level": lambda m: m.level,
    "max_hp": lambda m: m.max_hp,
    "ability": lambda m: m.ability,
    "item": lambda m: m.item,
    "first_turn_out": lambda m: m.first_turn,
}


def _stat_value(mon: Pokemon, stat: str) -> int:
    """A mon's stat: exact for our mons, median estimate for opponents (est ranges)."""
    known = (mon.stats or {}).get(stat)
    if known is not None:
        return known
    from .damagecalc import max_hp_range, stat_range

    return max_hp_range(mon)[1] if stat == "hp" else stat_range(mon, stat)[1]


@dataclass
class Ctx:
    battle: Battle
    it: Optional[Pokemon] = None  # bound by exists / switch_best


@dataclass(frozen=True)
class Side:
    """A `my.side` / `opponent.side` reference (SPEC §4.3), passed to side predicates."""

    is_opponent: bool


class InterpError(Exception):
    pass


def _bench(battle: Battle) -> list[Pokemon]:
    """Legal switch candidates = Riposte's `bench` domain for M0 (non-fainted, switchable)."""
    return list(battle.available_switches)


def _move_list(mon: Pokemon, battle: Battle) -> list[Move]:
    """Moves usable for scoring: our active uses the legal set; anyone else uses their known
    moves (opponent's are revealed-only, honoring the est discipline)."""
    if mon is battle.active_pokemon and battle.available_moves:
        return list(battle.available_moves)
    return list(mon.moves.values())


def _resolve_mon(path: list[str], ctx: Ctx) -> Pokemon:
    head = path[0]
    if head == "my" and path[1:2] == ["active"]:
        return ctx.battle.active_pokemon
    if head == "opponent" and path[1:2] == ["active"]:
        return ctx.battle.opponent_active_pokemon
    if head == "it":
        if ctx.it is None:
            raise InterpError("`it` referenced outside an exists/best binding")
        return ctx.it
    raise InterpError(f"unresolvable mon path: {path}")


def eval_expr(node: Any, ctx: Ctx) -> Any:
    k = node.kind

    if k == "lit":
        return node.value

    if k == "ref":
        path = node.path
        # side reference: my.side / opponent.side
        if len(path) == 2 and path[1] == "side":
            return Side(is_opponent=(path[0] == "opponent"))
        # a mon (no trailing field) or a mon field
        mon_len = 1 if path[0] == "it" else 2
        mon = _resolve_mon(path[:mon_len], ctx)
        rest = path[mon_len:]
        if not rest:
            return mon
        if len(rest) == 1:
            if rest[0] == "is_tera_available":  # battle-level, not a mon attribute
                return bool(getattr(ctx.battle, "can_tera", None))
            if rest[0] in _MON_FIELDS:
                return _MON_FIELDS[rest[0]](mon)
        if len(rest) == 2 and rest[0] == "boosts":
            return mon.boosts.get(rest[1], 0)
        if len(rest) == 2 and rest[0] == "stats":
            return _stat_value(mon, rest[1])
        raise InterpError(f"unknown field path: {path}")

    if k == "pred":
        return _eval_pred(node, ctx)

    if k == "outspeeds":
        a = eval_expr(node.left, ctx)
        b = eval_expr(node.right, ctx)
        return P.outspeeds(a, b)

    if k == "resolve":
        val = eval_expr(node.arg, ctx)
        if isinstance(val, bool):
            return val  # runtime tolerance; compiler forbids this (E031)
        if not isinstance(val, Tri):
            raise InterpError(f"resolver {node.op} applied to non-tribool {type(val)}")
        return getattr(val, node.op)()

    if k in ("and", "or"):
        vals = (eval_expr(o, ctx) for o in node.operands)
        if k == "and":
            return all(_as_bool(v) for v in vals)
        return any(_as_bool(v) for v in vals)

    if k == "not":
        return not _as_bool(eval_expr(node.operand, ctx))

    if k == "compare":
        return _compare(node.op, eval_expr(node.left, ctx), eval_expr(node.right, ctx))

    if k == "eff_cmp":
        cat = eval_expr(node.left, ctx)  # category string
        if node.op == "at_least":
            return P.eff_at_least(cat, node.right)
        if node.op == "at_most":
            return P.eff_at_most(cat, node.right)
        return cat == node.right

    if k == "exists":
        for cand in _bench(ctx.battle):
            if _as_bool(eval_expr(node.body, Ctx(ctx.battle, it=cand))):
                return True
        return False

    raise InterpError(f"unknown expr kind: {k}")


def _eval_pred(node: ir.Pred, ctx: Ctx) -> Any:
    """Dispatch a predicate call. Names + arities match the shared predicates.toml."""
    b = ctx.battle
    name = node.name

    def ev(i: int) -> Any:
        return eval_expr(node.args[i], ctx)

    if name == "can_ko":
        a, d = ev(0), ev(1)
        return P.can_ko(a, d, _move_list(a, b), b)
    if name == "guaranteed_ko":
        a, d = ev(0), ev(1)
        return P.guaranteed_ko(a, d, _move_list(a, b), b)
    if name == "resists":
        return P.resists(ev(0), ev(1))
    if name == "is_immune":
        return P.is_immune(ev(0), ev(1))
    if name == "matchup_score":
        m, o = ev(0), ev(1)
        return P.matchup_score(m, o, _move_list(m, b), b)
    if name == "effectiveness":
        return P.eff_category(P.type_multiplier(ev(0), ev(1)))
    if name == "knows":
        return P.knows(ev(0), ev(1))
    if name == "revealed":
        return P.revealed(ev(0), ev(1))
    if name == "hp_fraction":
        return ev(0).current_hp_fraction
    if name == "hazard_damage_on_switch":
        return P.hazard_damage_on_switch(ev(0), b)
    if name == "has_hazard":
        return P.has_hazard(ev(0).is_opponent, ev(1), b)
    if name == "hazard_layers":
        return P.hazard_layers(ev(0).is_opponent, ev(1), b)
    if name == "has_screen":
        return P.has_screen(ev(0).is_opponent, ev(1), b)
    if name == "damage_frac":
        return P.damage_frac_by_id(ev(0), ev(1), ev(2), b)
    raise InterpError(f"unknown or unsupported predicate at runtime: {name}")


# Predicate names the runtime dispatches (via _eval_pred, plus infix `outspeeds`). Kept in
# sync with predicates.toml by tests/test_predicates_toml.py so the compiler and runtime
# can't drift.
SUPPORTED_PREDICATES = frozenset(
    {
        "can_ko",
        "guaranteed_ko",
        "resists",
        "is_immune",
        "matchup_score",
        "effectiveness",
        "knows",
        "revealed",
        "hp_fraction",
        "hazard_damage_on_switch",
        "has_hazard",
        "hazard_layers",
        "has_screen",
        "damage_frac",
        "outspeeds",
    }
)


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, Tri):
        # A bare tribool in boolean position means the policy skipped a resolver; the
        # compiler rejects this (E030). Be conservative at runtime: treat unknown as False.
        return v.likely() and v.opp_favorable and v.my_favorable
    raise InterpError(f"expected bool, got {type(v)}")


def _compare(op: str, a: Any, b: Any) -> bool:
    ops = {
        "=": lambda: a == b,
        "!=": lambda: a != b,
        "<": lambda: a < b,
        "<=": lambda: a <= b,
        ">": lambda: a > b,
        ">=": lambda: a >= b,
    }
    return ops[op]()


# ─────────────────────────── action execution ───────────────────────────


def execute_action(action: Any, ctx: Ctx, player: Any) -> Optional[Any]:
    """Return a poke-env BattleOrder, or None if this action is not legal right now (the
    caller then falls through to the next rule / otherwise, per SPEC §4.1)."""
    battle = ctx.battle
    k = action.kind

    if k == "use_move":
        for mv in battle.available_moves:
            if mv.id == action.move_id:
                return _order(player, battle, mv, action.tera)
        return None

    if k == "use_strongest":
        if not battle.available_moves:
            return None
        target = _resolve_mon(action.target.path, ctx)
        mv, _ = P.best_move(battle.active_pokemon, target, list(battle.available_moves), battle)
        return _order(player, battle, mv, action.tera) if mv is not None else None

    if k == "switch_best":
        cands = _bench(battle)
        if not cands:
            return None
        keyed = [(eval_expr(action.by, Ctx(battle, it=c)), c) for c in cands]
        chosen = (max if action.order == "max" else min)(keyed, key=lambda t: t[0])[1]
        return player.create_order(chosen)

    raise InterpError(f"unknown action kind: {k}")


def _order(player: Any, battle: Battle, move: Move, tera: bool) -> Any:
    if tera and getattr(battle, "can_terastallize", False):
        return player.create_order(move, terastallize=True)
    return player.create_order(move)
