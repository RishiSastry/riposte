# Riposte — language overview

Riposte is a tiny declarative language for **Pokémon battle decision policies**. One file is
one bot. It compiles to a deterministic policy that plays `gen9randombattle` singles. There
are no loops, no variables, no user-defined functions — a program is just prioritized rules.

## Program shape

```
bot "my_bot" format gen9randombattle

on turn:
  rule <name>:
    when <condition>
    do <action>
  # ... more rules, top to bottom ...
  otherwise:
    do <action>

on forced_switch:
  rule <name>:
    when <condition>
    do <action>
  otherwise:
    do <action>
```

- A **header**: `bot "<name>" format gen9randombattle`.
- Up to two **blocks**: `on turn:` and `on forced_switch:`.
  - `on turn` fires for a normal action (move, switch, or terastallized move are legal).
  - `on forced_switch` fires after a faint / forced switch-out (only switches are legal —
    a move action here is a compile error, E041).
- Each block is an ordered list of **rules** plus a mandatory final **`otherwise`**.

## How a decision is made

1. Rules are checked **top to bottom**. The **first** rule whose `when` is true fires and its
   `do` action is taken. No scoring, no weights (quirk Q3 — rule order *is* priority).
2. Every block **must** end with `otherwise:` (no `when`). A missing `otherwise` is a compile
   error (E040) — this makes every policy total (always produces an action).
3. If a chosen action turns out to be illegal at runtime (Choice lock, disable, trapping),
   the runtime falls through to the next matching rule, then `otherwise`, then a random legal
   move as a last resort.

## The one idea that makes Riposte different

Battles are **partially observable**. Riposte encodes that in the type system: it separates
**facts** (things you truly know) from **estimates** (opponent stats, unrevealed moves). You
**cannot write a program that peeks** at hidden information, and you **cannot silently treat
an estimate as certain** — the compiler rejects both. Read `types_and_estimates` next.

## Discover the rest

Use `list_topics()` for the grains, `predicate_reference("<name>")` for a predicate's exact
signature and semantics, `explain_error("<code>")` when the compiler rejects your program,
and `check_program("<source>")` to compile it and see diagnostics.
