# Selectors and quantifiers

Riposte has no loops. Instead it gives you three bounded constructs over the bench, each of
which binds a candidate you refer to as **`it`**.

## `strongest_move against <target>`

Used inside a `use` action. Picks the current mon's move with the highest expected (median)
damage fraction against `<target>`:

```
do use strongest_move against opponent.active
```

## `best <domain> by <key>`

Used inside `switch_to`. Picks the member of `<domain>` (currently `bench`) that maximizes
`<key>`, an expression over the candidate `it`:

```
do switch_to best bench by matchup_score(it, opponent.active)
do switch_to best bench by hp_fraction(it)
```

`it` is bound only inside the `by <key>` expression. Using `it` anywhere else is an error
(E023).

## `exists <domain> <binder> where <predicate>`

A boolean quantifier — true if any member of the domain satisfies the predicate. The
`<binder>` names the candidate inside the `where` body:

```
when exists bench b where resists(b, opponent.active.primary_type)
```

Read it as: "is there a bench mon that resists the opponent's primary type?" This is the
usual guard before a defensive switch — check something *exists* to switch to, then switch to
the *best* one:

```
rule escape:
  when worst_case(opponent.active outspeeds my.active)
       and exists bench b where resists(b, opponent.active.primary_type)
  do switch_to best bench by matchup_score(it, opponent.active)
```
