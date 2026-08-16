# Deliberate quirks

Riposte makes four choices that are correct-but-unfamiliar. They come from the language's
goals, not from Pokémon convention. Getting them right is the difference between a program
that reads the docs and one that pattern-matches from the internet.

## Q1 — everything is a fraction

There are **no raw HP numbers** anywhere. All HP and damage quantities are fractions in
`[0, 1]` of max HP. `0.33` means "a third of max HP". `can_ko` compares damage fraction to
the target's `hp_fraction`. There is no `hp` field — only `hp_fraction` (and `max_hp` for
reference, but you rarely need it).

## Q2 — type effectiveness is categorical

`effectiveness(move_type, defender)` returns a **category**, never a number:

```
immune  <  strongly_resisted  <  resisted  <  neutral  <  super  <  overwhelming
```

Comparing effectiveness with a number (`effectiveness(...) > 2`) is a compile error (E032).
Use category comparisons instead:

```
when effectiveness(opponent.active.primary_type, my.active) at_least super
```

`strongly_resisted` is ≤0.25×, `resisted` is 0.5×, `super` is 2×, `overwhelming` is ≥4×.

## Q3 — rule order is priority

There is **no scoring and no weights**. Rules are tried top to bottom; the first true `when`
wins. If you want "prefer A, else B, else C", write three rules in that order. Do not try to
build a utility function — the language has no way to express one, on purpose.

## Q4 — resolvers are mandatory and non-redundant

An estimate-based comparison is a `tribool` and **must** be resolved with exactly one of
`likely` / `worst_case` / `best_case` (else E030). And a resolver on a value that is already
a fact is an error (E031). One resolver, exactly where uncertainty exists — no more, no less.

See `types_and_estimates` for the full treatment.
