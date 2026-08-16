"""Gen-9 damage calculation (SPEC §6, M2 deliverable — replaces the M0 heuristic).

Implements the standard gen-9 formula with STAB, type effectiveness, stat/boost handling,
burn, weather, and screens. Critical hits are excluded from estimates (SPEC). Opponent
stats/HP are unknown, so damage is returned as a **fraction of the defender's max HP**
(quirk Q1) over a (lo, mid, hi) range that folds in both the damage roll (85–100%) and
opponent stat/bulk uncertainty.

Determinism: no randomness; the roll is represented by its range endpoints. Same battle
state → same numbers. Unknown items/abilities are ignored (decision D-3, v1 default).

The core `base_damage` is validated against hand-checked textbook cases in
runtime/tests/test_damagecalc.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from poke_env.battle import (
    Move,
    MoveCategory,
    Pokemon,
    PokemonType,
    SideCondition,
    Status,
    Weather,
)

# ─────────────────────────── stat estimation ────────────────────────────


def _nonhp_stat(base: int, level: int, iv: int, ev: int, nature: float) -> int:
    return int((((2 * base + iv + ev // 4) * level) // 100 + 5) * nature)


def _hp_stat(base: int, level: int, iv: int, ev: int) -> int:
    return ((2 * base + iv + ev // 4) * level) // 100 + level + 10


def stat_range(mon: Pokemon, key: str) -> tuple[int, int, int]:
    """(lo, mid, hi) for a non-HP stat. Known (our) stats collapse to a point; opponent stats
    span an EV(0..252)/nature(0.9..1.1) envelope at IV 31. TODO(M2+): tighten with
    randombattle-constrained spreads."""
    known = (mon.stats or {}).get(key)
    if known is not None:
        return known, known, known
    base = mon.base_stats[key]
    lvl = mon.level
    return (
        _nonhp_stat(base, lvl, 31, 0, 0.9),
        _nonhp_stat(base, lvl, 31, 84, 1.0),
        _nonhp_stat(base, lvl, 31, 252, 1.1),
    )


def max_hp_range(mon: Pokemon) -> tuple[int, int, int]:
    """(lo, mid, hi) for max HP. Our mons expose it exactly; opponents are estimated."""
    if mon.max_hp:
        v = mon.max_hp
        return v, v, v
    base = mon.base_stats["hp"]
    lvl = mon.level
    return (
        _hp_stat(base, lvl, 31, 0),
        _hp_stat(base, lvl, 31, 84),
        _hp_stat(base, lvl, 31, 252),
    )


def _boost_mult(stage: int) -> float:
    return (2 + stage) / 2 if stage >= 0 else 2 / (2 - stage)


# ─────────────────────────── field context ──────────────────────────────


@dataclass
class FieldCtx:
    """The parts of battle state the damage formula needs. Built once per decision."""

    weather: Optional[Weather] = None
    my_screens: frozenset = frozenset()
    opp_screens: frozenset = frozenset()

    @classmethod
    def from_battle(cls, battle) -> "FieldCtx":
        weather = next(iter(battle.weather), None) if battle.weather else None
        screens = {SideCondition.REFLECT, SideCondition.LIGHT_SCREEN, SideCondition.AURORA_VEIL}
        my = frozenset(c for c in battle.side_conditions if c in screens)
        opp = frozenset(c for c in battle.opponent_side_conditions if c in screens)
        return cls(weather=weather, my_screens=my, opp_screens=opp)


# ─────────────────────────── the formula ────────────────────────────────


def base_damage(level: int, power: int, atk: int, dfn: int) -> int:
    """Core gen-9 base damage (before type/STAB/roll/etc.), with the formula's flooring.

    D = floor(floor(floor(2*L/5 + 2) * P * A / D) / 50) + 2
    """
    return ((2 * level // 5 + 2) * power * atk) // (50 * dfn) + 2


def _weather_mult(move_type: PokemonType, weather: Optional[Weather]) -> float:
    if weather in (Weather.RAINDANCE, Weather.PRIMORDIALSEA):
        if move_type == PokemonType.WATER:
            return 1.5
        if move_type == PokemonType.FIRE:
            return 0.5
    if weather in (Weather.SUNNYDAY, Weather.DESOLATELAND):
        if move_type == PokemonType.FIRE:
            return 1.5
        if move_type == PokemonType.WATER:
            return 0.5
    return 1.0


def _screen_mult(move: Move, defender_screens: frozenset) -> float:
    if not defender_screens:
        return 1.0
    if SideCondition.AURORA_VEIL in defender_screens:
        return 0.5
    if move.category == MoveCategory.PHYSICAL and SideCondition.REFLECT in defender_screens:
        return 0.5
    if move.category == MoveCategory.SPECIAL and SideCondition.LIGHT_SCREEN in defender_screens:
        return 0.5
    return 1.0


def damage_fraction(
    move: Move, attacker: Pokemon, defender: Pokemon, battle, field: Optional[FieldCtx] = None
) -> tuple[float, float, float]:
    """(lo, mid, hi) damage as a fraction of the defender's max HP. Endpoints fold the 85–100%
    roll together with attacker-stat / defender-bulk uncertainty (lo = weakest plausible hit,
    hi = strongest)."""
    if move.category == MoveCategory.STATUS or not move.base_power:
        return 0.0, 0.0, 0.0

    field = field or FieldCtx.from_battle(battle)
    physical = move.category == MoveCategory.PHYSICAL
    atk_key, def_key = ("atk", "def") if physical else ("spa", "spd")

    atk_lo, atk_mid, atk_hi = stat_range(attacker, atk_key)
    def_lo, def_mid, def_hi = stat_range(defender, def_key)
    hp_lo, hp_mid, hp_hi = max_hp_range(defender)

    # boosts
    a_boost = _boost_mult(attacker.boosts.get(atk_key, 0))
    d_boost = _boost_mult(defender.boosts.get(def_key, 0))

    # flat multipliers (independent of the lo/hi bound)
    stab = 1.5 if move.type in (attacker.type_1, attacker.type_2) else 1.0
    eff = defender.damage_multiplier(move)
    weather = _weather_mult(move.type, field.weather)
    burn = 0.5 if (physical and attacker.status == Status.BRN) else 1.0
    defender_screens = field.opp_screens if defender is battle.opponent_active_pokemon else field.my_screens
    screen = _screen_mult(move, defender_screens)
    flat = stab * eff * weather * burn * screen
    lvl = attacker.level

    def frac(atk_v: float, def_v: float, hp_v: int, roll: float) -> float:
        a = max(1, int(atk_v * a_boost))
        d = max(1, int(def_v * d_boost))
        dmg = base_damage(lvl, move.base_power, a, d) * flat * roll
        return dmg / hp_v if hp_v else 0.0

    hi = frac(atk_hi, def_lo, hp_lo, 1.0)  # strongest: our high atk, their low def/hp
    lo = frac(atk_lo, def_hi, hp_hi, 0.85)  # weakest
    mid = frac(atk_mid, def_mid, hp_mid, 0.925)
    return lo, mid, hi
