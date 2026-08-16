# State surface

What you can read in a `when` expression. Everything maps 1:1 onto what a legal player can
observe — the runtime never invents information.

## `my.active` — all facts

`species`, `types` / `primary_type`, `hp_fraction`, `max_hp`,
`stats.atk` / `stats.def` / `stats.spa` / `stats.spd` / `stats.spe` (post-nature, pre-boost),
`boosts.<stat>`, `status`, `ability`, `item`, `is_tera_available`, `first_turn_out`.

## `my.bench` — list of facts

Same surface as `my.active` (minus boosts). Fainted mons are excluded automatically. You
reach bench mons through selectors (`exists bench b where …`, `best bench by …`), not by
index.

## `opponent.active` — facts *and* estimates

| Property                         | Kind                         |
|----------------------------------|------------------------------|
| `species`, `types`, `primary_type` | **fact** (revealed once seen) |
| `hp_fraction`, `status`, `boosts` | **fact** (visible)           |
| `revealed_moves`                 | **fact**                     |
| `stats.*`                        | **est** (ranges from base stats + level) |
| `ability`                        | **est** (candidate set)      |
| `item`                           | **est**                      |

**`opponent.active.moves` is not accessible — it is unrevealed information (error E020).**
Ask about opponent moves only through `revealed(opponent.active, "move_id")`.

## `opponent.bench`

Only mons that have appeared; same estimate discipline as `opponent.active`.

## `field` (facts)

`weather`, `terrain`, `trick_room`, `turn`.

## `my.side` / `opponent.side` (facts)

Queried through side predicates, not fields: `has_hazard(side, <hazard>)`,
`hazard_layers(side, <hazard>)`, `has_screen(side, <screen>)`; plus `tailwind`.
Hazards: `stealth_rock`, `spikes`, `toxic_spikes`, `sticky_web`.
Screens: `reflect`, `light_screen`, `aurora_veil`.

```
when not opponent.side.has_hazard(stealth_rock)
when my.active.hp_fraction < 0.5
when opponent.active.status = brn
```
