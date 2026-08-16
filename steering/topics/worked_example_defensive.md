# Worked example — defensive / hazard control

A bot that sets hazards, escapes bad matchups, and presses when it has a KO. Every line is
legal Riposte; the annotations explain *why*.

```
bot "hazard_control" format gen9randombattle

on turn:
  rule lead_hazards:
    when my.active knows "stealthrock" and not opponent.side.has_hazard(stealth_rock)
    do use "stealthrock"

  rule escape_bad_matchup:
    when worst_case(opponent.active outspeeds my.active)
         and likely(can_ko(opponent.active, my.active))
         and exists bench b where resists(b, opponent.active.primary_type)
    do switch_to best bench by matchup_score(it, opponent.active)

  rule press_advantage:
    when likely(can_ko(my.active, opponent.active))
    do use strongest_move against opponent.active

  otherwise:
    do use strongest_move against opponent.active

on forced_switch:
  rule safe_pivot:
    when exists bench b where resists(b, opponent.active.primary_type)
    do switch_to best bench by matchup_score(it, opponent.active)

  otherwise:
    do switch_to best bench by hp_fraction(it)
```

## Why each piece is written that way

- **`lead_hazards`** — `knows` is a fact (`bool`), so no resolver. `has_hazard` reads your
  opponent's side; `not …` avoids double-stacking Stealth Rock.
- **`escape_bad_matchup`** — three conjuncts, each resolved at the right confidence:
  - `worst_case(opponent.active outspeeds my.active)` — *assume the worst* about a stat we
    only estimate (their Speed): treat them as faster.
  - `likely(can_ko(opponent.active, my.active))` — they *probably* KO us back.
  - `exists bench b where resists(b, …)` — and there's actually somewhere safe to go.
  Then it switches to the **best** such mon by `matchup_score`.
- **`press_advantage`** — if we *likely* KO, just attack. `likely` uses the median estimate.
- **`otherwise`** — mandatory; keeps hitting.
- **`on forced_switch`** — only switches are legal here. Prefer a resister; else preserve the
  healthiest mon (`hp_fraction(it)`).

## Common mistakes this avoids

- It never writes `can_ko(...)` bare in a `when` — that's a `tribool` (E030).
- It never writes `likely(resists(...))` — `resists` is already a fact (E031).
- It never reads `opponent.active.moves` — that's unrevealed (E020); it uses `knows`/`has_hazard`
  on facts instead.
