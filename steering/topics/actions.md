# Actions

Every rule's `do` is one action. There are three kinds.

## Use a specific move

```
do use "stealthrock"
do use "closecombat" with tera
```

The move id is the Showdown id (lowercase, no spaces). It is checked for legality at
runtime; if the mon doesn't have it (or it's disabled), the runtime falls through to the next
rule.

## Use the strongest move against a target

```
do use strongest_move against opponent.active
do use strongest_move against opponent.active with tera
```

`strongest_move` picks the move with the highest expected damage fraction against the target
(see `selectors`). This is the workhorse offensive action.

## Switch

```
do switch_to best bench by matchup_score(it, opponent.active)
do switch_to best bench by hp_fraction(it)
```

`switch_to best <domain> by <key>` picks the bench mon maximizing `<key>`, where `it` is the
candidate being scored (see `selectors`). In `on forced_switch` this is the *only* legal kind
of action.

## Terastallization

Append `with tera` to a `use` action to terastallize this turn (if available). It is
runtime-checked; if tera isn't available the move is used without it.
