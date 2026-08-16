# Worked example — hyper offense

A bot that terastallizes early to secure KOs, presses relentlessly, and pivots to a faster
attacker when it's outsped. Legal Riposte, annotated.

```
bot "hyper_offense" format gen9randombattle

on turn:
  rule tera_finish:
    when likely(can_ko(my.active, opponent.active)) and my.active.is_tera_available
    do use strongest_move against opponent.active with tera

  rule press_ko:
    when likely(can_ko(my.active, opponent.active))
    do use strongest_move against opponent.active

  rule find_faster_ko:
    when worst_case(opponent.active outspeeds my.active)
         and exists bench b where likely(can_ko(b, opponent.active))
    do switch_to best bench by matchup_score(it, opponent.active)

  otherwise:
    do use strongest_move against opponent.active

on forced_switch:
  rule best_attacker:
    when exists bench b where likely(can_ko(b, opponent.active))
    do switch_to best bench by matchup_score(it, opponent.active)

  otherwise:
    do switch_to best bench by matchup_score(it, opponent.active)
```

## Why each piece is written that way

- **`tera_finish` before `press_ko`** — rule order is priority (Q3). The tera version sits
  first so that *when tera is available and we have a KO*, we spend it; otherwise the next
  rule presses without tera. No weights, just ordering.
- **`likely(can_ko(...)) and my.active.is_tera_available`** — a resolved `tribool` and a
  plain fact `bool`, combined with `and`. No resolver on `is_tera_available` (that would be
  E031).
- **`find_faster_ko`** — note the resolver **inside** `exists`: `can_ko(b, opponent.active)`
  is a `tribool`, so the `exists … where` body wraps it in `likely(...)` to get a `bool`.
  This is the idiom for "is there a bench mon that probably KOs?"
- **`otherwise`** — always attack. Hyper offense rarely wants to sit.
- **`on forced_switch`** — bring in the mon most likely to KO; fall back to best overall
  matchup.

## The lesson

The difference between this bot and the defensive one is **rule order and which resolver**
you pick — not scores or weights. Offense leans on `likely`/`best_case`; defense leans on
`worst_case`.
