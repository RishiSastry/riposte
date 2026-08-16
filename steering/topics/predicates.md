# Predicates

Predicates are the built-in functions you call in `when` conditions and selector keys. They
are the only functions in the language — you cannot define your own.

For the exact signature, epistemic return kind, and an example of any predicate, call
`predicate_reference("<name>")`. The list:

| Predicate | Returns | Gist |
|-----------|---------|------|
| `damage_frac(move, atk, def)` | est frac | damage as a fraction of the defender's max HP |
| `can_ko(atk, def)` | tribool | best move's max roll ≥ defender hp_fraction |
| `guaranteed_ko(atk, def)` | tribool | best move's **min** roll ≥ defender hp_fraction |
| `a outspeeds b` | tribool | a is faster (post-boost, paralysis) — **infix** |
| `effectiveness(type, def)` | eff | categorical effectiveness (see quirks Q2) |
| `resists(mon, type)` | bool | mon takes <1× from type |
| `is_immune(mon, type)` | bool | mon takes 0× from type |
| `hazard_damage_on_switch(mon)` | frac | HP fraction lost switching into own hazards |
| `matchup_score(a, b)` | est num | composite score, mainly a `best … by` key |
| `hp_fraction(mon)` | frac | current HP as a fraction of max |
| `mon knows "id"` | bool | own mon has the move — **infix** |
| `revealed(mon, "id")` | bool | opponent has revealed the move this battle |
| `has_hazard(side, hazard)` | bool | side has the entry hazard |
| `hazard_layers(side, hazard)` | num | number of layers |
| `has_screen(side, screen)` | bool | side has the screen up |

**Honesty rule:** a predicate over any estimate argument returns an estimate / tribool. That
is why `can_ko` and `outspeeds` are `tribool` — the opponent's stats are estimates — and must
be wrapped in a resolver (`likely`/`worst_case`/`best_case`). `resists`/`is_immune` are plain
`bool` because typing is a fact.
