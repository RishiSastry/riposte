"""Hand-checked validation of the gen-9 damage core (SPEC §6)."""

from riposte_rt.damagecalc import _hp_stat, _nonhp_stat, base_damage


def test_base_damage_textbook_cases():
    # D = floor(floor(floor(2*L/5 + 2) * P * A / D) / 50) + 2, worked by hand:
    # L100 P80 A200 D100: (40+2)=42; 42*80*200=672000; /5000=134; +2 = 136
    assert base_damage(100, 80, 200, 100) == 136
    # L50 P100 A150 D120: 22; 22*100*150=330000; /6000=55; +2 = 57
    assert base_damage(50, 100, 150, 120) == 57
    # L100 P120 A300 D200: 42; 42*120*300=1512000; /10000=151; +2 = 153
    assert base_damage(100, 120, 300, 200) == 153


def test_base_damage_monotonic():
    # more power / attack → not less damage; more defense → not more damage
    assert base_damage(100, 90, 200, 100) >= base_damage(100, 80, 200, 100)
    assert base_damage(100, 80, 250, 100) >= base_damage(100, 80, 200, 100)
    assert base_damage(100, 80, 200, 150) <= base_damage(100, 80, 200, 100)


def test_stat_formulas():
    # Level-100, base 100, 31 IV, 0 EV, neutral nature → canonical 236.
    assert _nonhp_stat(100, 100, 31, 0, 1.0) == 236
    # Max-HP stat: base 100, level 100, 31 IV, 0 EV → 341.
    assert _hp_stat(100, 100, 31, 0) == 341
    # EVs raise the stat.
    assert _nonhp_stat(100, 100, 31, 252, 1.0) > _nonhp_stat(100, 100, 31, 0, 1.0)
