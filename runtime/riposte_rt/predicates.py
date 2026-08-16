"""Predicate implementations + the tribool type.

⚠️ M0 SCOPE: the damage/speed models here are deliberately COARSE heuristics, good enough to
drive a policy that beats RandomPlayer and to exercise the fact/est/tribool machinery
end-to-end. The real gen-9 damage formula (STAB, type chart, boosts, burn, weather, screens,
hand-checked validation) is an M2 deliverable (SPEC §6). Every M0 shortcut is marked
`TODO(M2)`.
"""

from __future__ import annotations

from dataclasses import dataclass

from poke_env.battle import Move, MoveCategory, Pokemon, PokemonType

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

_SCALE = 220.0  # M0 tuning constant so a neutral 80 BP move ≈ 0.36 of max HP.


def damage_frac(move: Move, attacker: Pokemon, defender: Pokemon) -> tuple[float, float, float]:
    """(lo, mid, hi) fraction of the DEFENDER's max HP (SPEC quirk Q1: everything is a
    fraction). M0 heuristic: base_power · STAB · type-effectiveness, scaled, with an
    85%–100% roll band standing in for both damage rolls and defender-bulk uncertainty.

    TODO(M2): real formula with attacker/defender stats, boosts, burn, weather, screens.
    """
    if move.category == MoveCategory.STATUS or not move.base_power:
        return 0.0, 0.0, 0.0
    stab = 1.5 if move.type in (attacker.type_1, attacker.type_2) else 1.0
    eff = defender.damage_multiplier(move)
    hi = move.base_power * stab * eff / _SCALE
    lo = hi * 0.85
    mid = hi * 0.925
    return lo, mid, hi


def best_move(attacker: Pokemon, defender: Pokemon, moves: list[Move]) -> tuple[Move | None, float]:
    """argmax expected (median) damage_frac over `moves` (SPEC: strongest_move selector)."""
    best: Move | None = None
    best_mid = -1.0
    for m in moves:
        _, mid, _ = damage_frac(m, attacker, defender)
        if mid > best_mid:
            best, best_mid = m, mid
    return best, max(best_mid, 0.0)


# ──────────────────────────── predicates ────────────────────────────────


def can_ko(attacker: Pokemon, defender: Pokemon, moves: list[Move]) -> Tri:
    """tribool: max-roll damage of attacker's best move ≥ defender hp_fraction (SPEC §4.4)."""
    lo = hi = mid = 0.0
    for m in moves:
        l, mi, h = damage_frac(m, attacker, defender)
        if h > hi:
            lo, mid, hi = l, mi, h
    hp = defender.current_hp_fraction
    # opp_favorable = opponent bulky (our low roll); my_favorable = our high roll.
    return Tri(median=mid >= hp, opp_favorable=lo >= hp, my_favorable=hi >= hp)


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


def matchup_score(mine: Pokemon, opp: Pokemon, my_moves: list[Move]) -> float:
    """Composite used as a `best ... by` key (SPEC §4.4). Offense − incoming threat + hp/speed
    nudges. Coarse by design; it only needs to order switch candidates sensibly."""
    _, offense = best_move(mine, opp, my_moves) if my_moves else (None, 0.0)
    threat = max(
        (type_multiplier(t, mine) for t in (opp.type_1, opp.type_2) if t is not None),
        default=1.0,
    )
    my_lo, _, _ = _known_or_est_speed(mine)
    op_lo, _, _ = _known_or_est_speed(opp)
    speed_edge = 0.15 if my_lo > op_lo else 0.0
    return offense - 0.4 * threat + 0.3 * mine.current_hp_fraction + speed_edge
