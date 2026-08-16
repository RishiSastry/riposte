# riposte-rt — runtime

Thin interpreter over the policy IR (`policy.json`). The Rust compiler *emits* the IR;
this package *interprets* it and plays battles via poke-env. See [SPEC.md §6](../SPEC.md).

| Module            | Role                                                                    |
|-------------------|-------------------------------------------------------------------------|
| `ir.py`           | Policy IR schema (pydantic, versioned) — the compiler↔runtime contract. |
| `predicates.py`   | Predicate library + the `Tri` tribool type; damage/speed/effectiveness. |
| `interp.py`       | Evaluate the condition expr tree; execute actions → poke-env orders.     |
| `player.py`       | `RipostePlayer(Player)`: block select, top-down rules, fallback, traces. |

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

## ⚠️ Deliberate M0 shortcuts (to replace in M2)

These keep the skeleton small while exercising the full IR→interp→battle path. All are
marked `TODO(M2)` in code; the real versions land with the type system + predicate work:

- **Damage calc is a coarse heuristic** (`base_power · STAB · type-eff`, scaled, with an
  85–100% roll band standing in for both damage rolls *and* defender-bulk uncertainty). The
  real gen-9 formula (stats, boosts, burn, weather, screens; hand-checked cases) is M2.
- **Opponent stat ranges** use a wide EV/IV/nature envelope, not randombattle-constrained
  spreads.
- **`outspeeds`** ignores tailwind / trick room.
- The `Tri` tribool folds defender-bulk uncertainty into the roll band rather than modeling
  the est range per stat.

## Note for the compiler (M1/M2)

`ir.py` is the authoritative IR shape the emitter must target. Predicate *signatures* will
also live in a shared `predicates.toml` (SPEC §4.4) so Rust and Python don't drift; the
implementations here are the Python side of that contract.
