# Types and estimates (the epistemic core)

Riposte layers two **epistemic kinds** over its base types (`num`, `frac`, `bool`, `type`,
`status`, `mon`, `move`, `eff`):

- **fact T** — exactly known. Everything about your side; revealed opponent properties
  (species, typing once seen, revealed moves, visible status/boosts, HP fraction).
- **est T** — known only as a range or candidate set. Opponent stats (ranges from species +
  level), unrevealed moves, unconfirmed ability/item.

## tribool: the type of an uncertain comparison

Any comparison where **either side is an estimate** does not produce `bool` — it produces
**`tribool`** (yes / no / unknown). For example, `can_ko(my.active, opponent.active)` is a
`tribool`, because the opponent's Def/SpD are estimates, so you can't be *certain* it KOs.

A `when` clause requires `bool`. **You must resolve a `tribool` into a `bool`** with exactly
one of three operators:

| Resolver          | Meaning                                                              |
|-------------------|---------------------------------------------------------------------|
| `likely(x)`       | true if yes across the whole range, or yes at the **median** estimate |
| `worst_case(x)`   | resolve assuming the opponent's **most favorable** value             |
| `best_case(x)`    | resolve assuming **your** most favorable value                       |

```
when likely(can_ko(my.active, opponent.active))          # press when it probably KOs
when worst_case(opponent.active outspeeds my.active)     # assume they're faster (be safe)
```

## Two rules the compiler enforces

1. **A bare `tribool` in a `when` is an error (E030).** You must wrap it in a resolver.
   The compiler even tells you which three to choose from.
2. **A resolver on something already a `fact` is an error (E031).** `likely(resists(...))`
   is wrong — `resists` returns a plain `bool`, so there is no uncertainty to resolve. Don't
   cargo-cult resolvers onto everything.

This is the "can't express the lie" property: there is **no syntax** for peeking at hidden
info, and you **cannot** treat an estimate as if it were certain.

## `likely` uses the median (v1)

`likely` resolves an estimate at its **median** value (for stat ranges, the median stat).
So `likely(can_ko(...))` means "KOs assuming the opponent has middle-of-the-road bulk."
Use `worst_case`/`best_case` when you need the extremes.
