"""Predicate implementations + the tribool type.

The Python side of the `predicates.toml` contract (SPEC §4.4): every predicate the compiler
type-checks is implemented here with matching arity. Damage uses the real gen-9 calc in
`damagecalc.py` (M2). Speed estimation remains a documented simplification (TODO(M2+):
tailwind/trick-room in `outspeeds`).
"""

from __future__ import annotations

from dataclasses import dataclass

from poke_env.battle import Move, MoveCategory, Pokemon, PokemonType, SideCondition

from . import damagecalc
from .damagecalc import FieldCtx

# hazard / screen atom (as written in .rpo, lowered to a str by the compiler) → poke-env enum.
_HAZARDS = {
    "stealth_rock": SideCondition.STEALTH_ROCK,
    "spikes": SideCondition.SPIKES,
    "toxic_spikes": SideCondition.TOXIC_SPIKES,
    "sticky_web": SideCondition.STICKY_WEB,
}
_SCREENS = {
    "reflect": SideCondition.REFLECT,
    "light_screen": SideCondition.LIGHT_SCREEN,
    "aurora_veil": SideCondition.AURORA_VEIL,
}

# ─────────────────────────────── tribool ────────────────────────────────


@dataclass(frozen=True)
class Tri:
    """A tribool carried as three resolutions of the same predicate over an estimate range.

    - `median`: predicate under the opponent's median (expected) values.
    - `opp_favorable`: under the opponent's most-favorable-to-them values (their best case).
    - `my_favorable`: under my most-favorable values.

    Resolvers (SPEC §4.2):
      likely      → yes over the whole range, or yes at the median
      worst_case  → resolve assuming the opponent's most favorable value
      best_case   → resolve assuming my most favorable value
    """

    median: bool
    opp_favorable: bool
    my_favorable: bool

    def likely(self) -> bool:
        whole_range_yes = self.opp_favorable and self.my_favorable
        return whole_range_yes or self.median

    def worst_case(self) -> bool:
        return self.opp_favorable

    def best_case(self) -> bool:
        return self.my_favorable


# ─────────────────────────── stat estimation ────────────────────────────


def _stat_from_base(base: int, level: int, iv: int, ev: int, nature: float) -> int:
    """Standard gen-9 non-HP stat formula."""
    return int((((2 * base + iv + ev // 4) * level) // 100 + 5) * nature)


def est_speed_range(mon: Pokemon) -> tuple[int, int, int]:
    """(lo, median, hi) speed estimate for a mon whose EVs/IVs/nature are unknown.

    TODO(M2): randombattle sets are constrained (known spreads by generation) — tighten.
    """
    base = mon.base_stats["spe"]
    lvl = mon.level
    lo = _stat_from_base(base, lvl, 31, 0, 0.9)
    mid = _stat_from_base(base, lvl, 31, 84, 1.0)
    hi = _stat_from_base(base, lvl, 31, 252, 1.1)
    return lo, mid, hi


def _known_or_est_speed(mon: Pokemon) -> tuple[int, int, int]:
    """Our mons expose real stats (fact); opponents give an est range."""
    spe = (mon.stats or {}).get("spe")
    if spe is not None:
        return spe, spe, spe
    return est_speed_range(mon)


def _boost_mult(stage: int) -> float:
    return (2 + stage) / 2 if stage >= 0 else 2 / (2 - stage)


def _effective_speed(mon: Pokemon, spe: int) -> float:
    s = spe * _boost_mult(mon.boosts.get("spe", 0))
    if mon.status is not None and getattr(mon.status, "name", "") == "PAR":
        s *= 0.5  # TODO(M2): tailwind, trick room, Quick Feet, etc.
    return s


# ─────────────────────────── effectiveness ──────────────────────────────

_EFF_ORDER = ["immune", "strongly_resisted", "resisted", "neutral", "super", "overwhelming"]


def eff_category(multiplier: float) -> str:
    if multiplier == 0:
        return "immune"
    if multiplier <= 0.25:
        return "strongly_resisted"
    if multiplier <= 0.5:
        return "resisted"
    if multiplier < 2:
        return "neutral"
    if multiplier < 4:
        return "super"
    return "overwhelming"


def eff_at_least(cat: str, threshold: str) -> bool:
    return _EFF_ORDER.index(cat) >= _EFF_ORDER.index(threshold)


def eff_at_most(cat: str, threshold: str) -> bool:
    return _EFF_ORDER.index(cat) <= _EFF_ORDER.index(threshold)


def type_multiplier(attacking_type: PokemonType, defender: Pokemon) -> float:
    return defender.damage_multiplier(attacking_type)


# ───────────────────────────── damage calc ──────────────────────────────
# Real gen-9 formula lives in damagecalc.py (M2). These are thin wrappers threading the
# battle-derived field context (weather/screens) through.


def damage_frac(
    move: Move, attacker: Pokemon, defender: Pokemon, battle, field=None
) -> tuple[float, float, float]:
    """(lo, mid, hi) damage as a fraction of the defender's max HP (quirk Q1)."""
    return damagecalc.damage_fraction(move, attacker, defender, battle, field)


def damage_frac_by_id(move_id: str, attacker: Pokemon, defender: Pokemon, battle) -> float:
    """Runtime form of damage_frac: resolve the move by id off the attacker and return the
    median fraction (D-2 median convention; the compiler tracks the full est range)."""
    move = attacker.moves.get(move_id)
    if move is None:
        return 0.0
    _, mid, _ = damage_frac(move, attacker, defender, battle)
    return mid


def best_move(
    attacker: Pokemon, defender: Pokemon, moves: list[Move], battle, field=None
) -> tuple[Move | None, float]:
    """argmax expected (median) damage_frac over `moves` (SPEC: strongest_move selector)."""
    field = field or FieldCtx.from_battle(battle)
    best: Move | None = None
    best_mid = -1.0
    for m in moves:
        _, mid, _ = damage_frac(m, attacker, defender, battle, field)
        if mid > best_mid:
            best, best_mid = m, mid
    return best, max(best_mid, 0.0)


# ──────────────────────────── predicates ────────────────────────────────


def _best_damage_bounds(
    attacker: Pokemon, defender: Pokemon, moves: list[Move], battle, field
) -> tuple[float, float, float]:
    """(lo, mid, hi) damage fraction of the attacker's most damaging move (by hi roll)."""
    lo = hi = mid = 0.0
    for m in moves:
        l, mi, h = damage_frac(m, attacker, defender, battle, field)
        if h > hi:
            lo, mid, hi = l, mi, h
    return lo, mid, hi


def can_ko(attacker: Pokemon, defender: Pokemon, moves: list[Move], battle) -> Tri:
    """tribool: max-roll damage of attacker's best move ≥ defender hp_fraction (SPEC §4.4)."""
    field = FieldCtx.from_battle(battle)
    lo, mid, hi = _best_damage_bounds(attacker, defender, moves, battle, field)
    hp = defender.current_hp_fraction
    # opp_favorable = opponent bulky (our low roll); my_favorable = our high roll.
    return Tri(median=mid >= hp, opp_favorable=lo >= hp, my_favorable=hi >= hp)


def guaranteed_ko(attacker: Pokemon, defender: Pokemon, moves: list[Move], battle) -> Tri:
    """tribool: min-roll damage of attacker's best move ≥ defender hp_fraction (SPEC §4.4)."""
    field = FieldCtx.from_battle(battle)
    lo, mid, hi = _best_damage_bounds(attacker, defender, moves, battle, field)
    hp = defender.current_hp_fraction
    # guaranteed uses the low roll: yes only if even our weakest roll KOs.
    return Tri(median=lo >= hp, opp_favorable=lo >= hp, my_favorable=mid >= hp)


def outspeeds(a: Pokemon, b: Pokemon) -> Tri:
    """tribool: a is faster than b, post-boost/paralysis. TODO(M2): tailwind, trick room."""
    a_lo, a_mid, a_hi = _known_or_est_speed(a)
    b_lo, b_mid, b_hi = _known_or_est_speed(b)
    a_med = _effective_speed(a, a_mid)
    # median vs opponent median; opp_favorable = b fastest & a slowest; my_favorable = reverse
    return Tri(
        median=a_med > _effective_speed(b, b_mid),
        opp_favorable=_effective_speed(a, a_lo) > _effective_speed(b, b_hi),
        my_favorable=_effective_speed(a, a_hi) > _effective_speed(b, b_lo),
    )


def resists(mon: Pokemon, atk_type: PokemonType) -> bool:
    m = mon.damage_multiplier(atk_type)
    return 0 < m < 1


def is_immune(mon: Pokemon, atk_type: PokemonType) -> bool:
    return mon.damage_multiplier(atk_type) == 0


def knows(mon: Pokemon, move_id: str) -> bool:
    """The (own) mon has the given move id (SPEC §4.4)."""
    return move_id in mon.moves


def revealed(mon: Pokemon, move_id: str) -> bool:
    """The opponent has revealed the given move id — the only honest opponent-move query."""
    return move_id in mon.moves


def _side_conditions(is_opponent: bool, battle) -> dict:
    return battle.opponent_side_conditions if is_opponent else battle.side_conditions


def has_hazard(is_opponent: bool, hazard: str, battle) -> bool:
    sc = _side_conditions(is_opponent, battle)
    return _HAZARDS.get(hazard) in sc


def hazard_layers(is_opponent: bool, hazard: str, battle) -> int:
    sc = _side_conditions(is_opponent, battle)
    return sc.get(_HAZARDS.get(hazard), 0)


def has_screen(is_opponent: bool, screen: str, battle) -> bool:
    sc = _side_conditions(is_opponent, battle)
    return _SCREENS.get(screen) in sc


def hazard_damage_on_switch(mon: Pokemon, battle) -> float:
    """Fraction of max HP `mon` loses switching into OUR-side hazards (own hazards are facts).
    Approximate (M2): Stealth Rock scaled by Rock effectiveness; Spikes by layers if grounded."""
    sc = battle.side_conditions
    dmg = 0.0
    if SideCondition.STEALTH_ROCK in sc:
        dmg += 0.125 * mon.damage_multiplier(PokemonType.ROCK)
    grounded = PokemonType.FLYING not in (mon.type_1, mon.type_2)
    if grounded and SideCondition.SPIKES in sc:
        layers = sc.get(SideCondition.SPIKES, 1)
        dmg += {1: 1 / 8, 2: 1 / 6, 3: 1 / 4}.get(layers, 1 / 8)
    return min(dmg, 1.0)


def matchup_score(mine: Pokemon, opp: Pokemon, my_moves: list[Move], battle) -> float:
    """Composite used as a `best ... by` key (SPEC §4.4). Offense − incoming threat + hp/speed
    nudges. Coarse by design; it only needs to order switch candidates sensibly."""
    _, offense = best_move(mine, opp, my_moves, battle) if my_moves else (None, 0.0)
    threat = max(
        (type_multiplier(t, mine) for t in (opp.type_1, opp.type_2) if t is not None),
        default=1.0,
    )
    my_lo, _, _ = _known_or_est_speed(mine)
    op_lo, _, _ = _known_or_est_speed(opp)
    speed_edge = 0.15 if my_lo > op_lo else 0.0
    return offense - 0.4 * threat + 0.3 * mine.current_hp_fraction + speed_edge
