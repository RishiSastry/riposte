# riposte-rt — runtime

Thin interpreter over the policy IR (`policy.json`). The Rust compiler *emits* the IR;
this package *interprets* it and plays battles via poke-env. See [SPEC.md §6](../SPEC.md).

| Module            | Role                                                                    |
|-------------------|-------------------------------------------------------------------------|
| `ir.py`           | Policy IR schema (pydantic, versioned) — the compiler↔runtime contract. |
| `predicates.py`   | Predicate library + the `Tri` tribool type. Python side of `predicates.toml`. |
| `damagecalc.py`   | **M2:** real gen-9 damage formula (stats, STAB, type chart, boosts, burn, weather, screens). |
| `interp.py`       | Evaluate the condition expr tree; execute actions → poke-env orders.     |
| `player.py`       | `RipostePlayer(Player)`: block select, top-down rules, fallback, traces. A rule that errors at runtime is caught and skipped (never stalls a battle) — a policy the runtime can't interpret loses, it doesn't hang the eval harness. |

## M0 status: walking skeleton ✅

The hand-written [`examples/m0_skeleton.policy.json`](../examples/m0_skeleton.policy.json)
(a faithful encoding of the SPEC §4.1 example) beats `RandomPlayer` well above the >70%/100
gate. Run it:

```bash
# terminal 1: local Showdown (pinned commit in ../.showdown-commit)
cd ../pokemon-showdown && node pokemon-showdown start --no-security
# terminal 2:
source .venv/bin/activate && cd ..
python scripts/m0_gate.py --n 100            # vs RandomPlayer (the gate)
python scripts/m0_gate.py --n 100 --opponent max   # vs MaxBasePowerPlayer
```

## M2 status: real damage calc ✓

`damagecalc.py` implements the gen-9 formula (validated against hand-checked textbook cases
in `tests/test_damagecalc.py`). Predicate names/arities are checked against the shared
`predicates.toml` by `tests/test_predicates_toml.py` so the compiler and runtime can't
drift. Run tests: `python -m pytest tests/ -q`.

### Remaining documented simplifications

- **Opponent stat/HP ranges** use a wide EV/IV/nature envelope, not randombattle-constrained
  spreads (TODO(M2+)).
- **`outspeeds`** ignores tailwind / trick room (TODO(M2+)).
- **Unknown items/abilities** are ignored in the damage calc (decision D-3, v1 default).
- Runtime est-range comparisons on `damage_frac` use the median (D-2); the *compiler* tracks
  the full est range and enforces resolver discipline.

`ir.py` is the authoritative IR shape the emitter targets; `predicates.toml` (repo root) is
the shared signature contract (SPEC §4.4).
