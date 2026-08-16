# Riposte: An Agent-Native DSL for Pokémon Battle Policies

> Working name. Alternatives: Pivot, Parley. Decide before repo creation (D-1).

## 1. Thesis and framing

Riposte is a small declarative language for expressing Pokémon battle decision policies. A
program compiles to a deterministic policy that plays real battles on Pokémon Showdown via
poke-env. No model has ever seen this language, which makes it a clean instrument for the
question the project actually answers:

**Given a language an LLM has never seen, which steering strategy best teaches an agent to
write correct, competitive programs in it?**

Prior work (Anka, arXiv:2512.23214) established that LLMs can learn a novel DSL from a
static in-context syntax guide (99.9% parse success, single-shot prompting, data
transformation domain, output-equality scoring). This project holds that result as a given
and measures what Anka did not:

1. **Steering delivery as the independent variable.** Static docs dump vs. progressive
   discovery via MCP tools vs. compiler-error repair loops, and combinations.
2. **Ground truth beyond output matching.** Programs are scored by win rate over many
   battles against fixed baselines. Semantic bugs that compile and lose are invisible to
   parse/execute metrics and central here.
3. **Epistemic honesty in the type system.** Battles are partially observable. The language
   distinguishes facts from estimates at the type level; the compiler rejects programs that
   treat guesses as facts.
4. **Compile-time LLM vs. runtime LLM.** Contrast with PokéLLMon/PokéChamp lineage where an
   LLM is consulted every turn. Here the LLM writes the policy once; execution is
   deterministic and free.

Deliverables: the compiler (Rust), runtime (Python), MCP server (Python), eval harness
(Python), and a blog post on eval learnings. The DSL/compiler learnings post comes later.

## 2. Non-goals (v1)

- No doubles. Singles only.
- No team building. Format is `gen9randombattle`: Showdown assigns teams.
- No probabilistic opponent modeling beyond stat ranges derivable from species/level.
- No ladder play in the eval loop. Local headless server only. (Laddering a hand-written
  showcase bot is a fun side quest, not part of evals.)
- No imperative constructs: no loops, no user-defined functions, no variables in v1.
- The language is not trying to be pleasant for humans. Agent ergonomics win every tie.

## 3. Architecture

```
┌─────────────┐   .rpo source    ┌──────────────────┐   policy.json (IR)   ┌────────────────┐
│  LLM agent   │ ───────────────> │  riposte-c (Rust) │ ──────────────────> │ runtime (Py)    │
│  (writes DSL)│ <─────────────── │  parse/check/emit │                     │ poke-env Player │
└─────────────┘  diagnostics.json└──────────────────┘                     │ interprets IR   │
       ▲                                                                   └──────┬─────────┘
       │            MCP server (Py): progressive language discovery               │ websocket
       └──────────────────────────────────────────────────────────────────┐ ┌─────▼─────────┐
                                                                          │ │ local Showdown │
                                              eval harness (Py) ──────────┘ │ server (node)  │
                                                                            └───────────────┘
```

Key decision: **the compiler emits a JSON policy IR, not Python code.** The Python runtime
is a thin interpreter over the IR. Rationale: keeps codegen trivial and versioned, makes
compiled artifacts inspectable/diffable for evals, and keeps all semantic checking in the
Rust front end where the structured errors live.

Repo layout (single repo):

```
riposte/
├── SPEC.md                  # this file
├── compiler/                # Rust workspace: riposte-c
│   ├── crates/lexer/
│   ├── crates/parser/       # hand-written recursive descent
│   ├── crates/typeck/
│   ├── crates/emit/
│   └── crates/diagnostics/  # error codes, spans, JSON rendering
├── runtime/                 # Python package: riposte-rt
│   ├── riposte_rt/ir.py     # IR schema (pydantic), versioned
│   ├── riposte_rt/interp.py # per-turn IR evaluation
│   ├── riposte_rt/predicates.py  # damage calc, speed, effectiveness
│   └── riposte_rt/player.py # poke-env Player subclass
├── mcp/                     # riposte-mcp: progressive discovery server
├── evals/                   # harness, tasks, baselines, analysis
│   ├── tasks/               # natural-language strategy briefs
│   ├── conditions/          # steering condition configs
│   └── golden/              # reference .rpo programs
├── steering/                # language docs in three grains (see §8)
└── examples/                # example .rpo programs
```

Tech choices: Rust with `logos` for lexing, hand-written recursive descent for parsing
(maximum control over recovery and error quality; no parser-generator magic to explain in
the blog post). `serde` for IR/diagnostics JSON. Python 3.11+, `poke-env` latest,
`pydantic` for IR schema validation, MCP via the official Python SDK. Local Showdown server
pinned to a specific commit for reproducibility.

## 4. Language specification

### 4.1 Program shape

One file = one bot. Extension `.rpo`. A program has a header and two rule blocks:

```
bot "hazard_control" format gen9randombattle

on turn:
  rule lead_hazards:
    when my.active knows "stealthrock" and not opponent.side.has_hazard(stealth_rock)
    do use "stealthrock"

  rule escape_bad_matchup:
    when worst_case(opponent.active outspeeds my.active)
         and likely(can_ko(opponent.active, my.active))
         and exists bench b where resists(b, opponent.active.primary_type)
    do switch_to best bench by matchup_score(it, opponent.active)

  rule press_advantage:
    when likely(can_ko(my.active, opponent.active))
    do use strongest_move against opponent.active

  otherwise:
    do use strongest_move against opponent.active

on forced_switch:
  rule safe_pivot:
    when exists bench b where resists(b, opponent.active.primary_type)
    do switch_to best bench by matchup_score(it, opponent.active)

  otherwise:
    do switch_to best bench by hp_fraction(it)
```

Semantics:

- Rules in a block are evaluated **top to bottom**; the first rule whose `when` clause is
  true fires and its `do` action is taken. No fallthrough, no weights.
- Every block **must** end with an `otherwise` rule (no `when`). Missing `otherwise` is a
  compile error (E040). This makes every policy total.
- `on turn` fires when the server requests a normal action: legal actions are moves,
  switches, and terastallize-augmented moves. `on forced_switch` fires after a faint or a
  forced switch-out: legal actions are switches only. Using a move action in
  `forced_switch` is a compile error (E041). The two blocks are separate rule lists and do
  not share rules.
- If a fired action turns out to be illegal at runtime despite checks (edge cases: Choice
  lock, disable, trapping), the runtime falls through to the next matching rule, and
  ultimately to `otherwise`; if `otherwise` is also illegal, the runtime picks a random
  legal action and logs a `runtime_fallback` event. Fallback frequency is an eval metric.

### 4.2 Type system: facts and estimates

Two epistemic kinds layered over base types (`num`, `frac`, `bool`, `type`, `status`,
`mon`, `move`):

- **fact T** — exactly known. Everything about my side; revealed properties of the
  opponent (species, typing once seen, revealed moves, visible status/boosts, HP
  fraction).
- **est T** — known only as a range or candidate set. Opponent stats (ranges from species
  base stats + level), unrevealed moves, unconfirmed ability (candidate set), unconfirmed
  item.

Rules:

1. Comparisons where either operand is `est` produce **`tribool`** (yes / no / unknown),
   not `bool`.
2. The `when` clause requires `bool`. A `tribool` must be resolved with exactly one of
   three resolution operators:
   - `likely(x)` — true if yes over the whole estimate range, or yes for the median of the
     range. (Precise semantics per predicate documented in steering; median stat
     assumption for stat ranges.)
   - `worst_case(x)` — resolves assuming the opponent's most favorable value.
   - `best_case(x)` — resolves assuming my most favorable value.
3. Using a `tribool` where `bool` is required is a compile error (E030) with a hint naming
   the three resolvers. Applying a resolver to a plain `bool` is also an error (E031,
   "already a fact") — this catches agents cargo-culting resolvers everywhere.
4. Predicates are honest about their inputs: a predicate over any `est` argument returns
   `est`/`tribool`. `can_ko(my.active, opponent.active)` is `tribool` because opponent
   Def/SpD are ranges.

This is the "can't express the lie" property: the compiler statically rejects programs
that peek (there is no syntax for unrevealed information) and programs that treat
uncertainty as certainty (E030).

### 4.3 State surface

Namespaces available in `when` expressions. Everything maps 1:1 onto poke-env `Battle`
fields; the runtime never synthesizes information a legal player could not know.

**`my.active`** (all facts): `species`, `types` / `primary_type`, `hp_fraction`,
`max_hp`, `stats.atk/def/spa/spd/spe` (post-nature, pre-boost), `boosts.*`, `status`,
`ability`, `item`, `moves` (list with `pp`, `base_power`, `move_type`, `category`),
`is_tera_available`, `first_turn_out`.

**`my.bench`** (list of facts): same surface as active minus boosts; `fainted` excluded
from `bench` automatically.

**`opponent.active`**: `species` (fact), `types` (fact), `hp_fraction` (fact),
`revealed_moves` (facts), `status` (fact), `boosts` (fact), `stats.*` (est ranges),
`ability` (est: candidate set), `item` (est). Accessing `opponent.active.moves` (as
opposed to `revealed_moves`) is a compile error (E020, "unrevealed information").

**`opponent.bench`**: only mons that have appeared; same est discipline.

**`field`** (facts): `weather`, `terrain`, `trick_room`, `turn`. **`my.side` /
`opponent.side`** (facts): `has_hazard(h)`, `hazard_layers(h)`, `has_screen(s)`,
`tailwind`.

### 4.4 Predicate library (v1)

All damage quantities are **fractions of the target's max HP** (quirk Q1 below).

- `damage_frac(move, attacker, defender) -> est frac` — min/max roll range via standard
  gen 9 damage formula with STAB, type effectiveness, boosts, weather, screens, burn.
  Items/abilities: only revealed/known ones applied; unknown treated as range-widening
  where feasible in v1, else ignored and documented.
- `can_ko(attacker, defender) -> tribool` — max-roll damage of attacker's best move ≥
  defender `hp_fraction`.
- `guaranteed_ko(attacker, defender) -> tribool` — min-roll of best move ≥ `hp_fraction`.
- `a outspeeds b -> tribool` — post-boost, post-paralysis, tailwind/trick-room aware.
- `effectiveness(move_type, defender) -> eff` — **categorical** (quirk Q2): `immune`,
  `strongly_resisted` (≤0.25x), `resisted` (0.5x), `neutral`, `super` (2x), `overwhelming`
  (≥4x). No numeric multipliers in the language.
- `resists(mon, type) -> bool`, `is_immune(mon, type) -> bool`.
- `hazard_damage_on_switch(mon) -> frac` (fact — own side hazards are known).
- `matchup_score(a, b) -> est num` — documented composite (offensive effectiveness both
  directions, speed, hp). Exists mainly as a `best ... by` key.
- `knows(mon, "move_id") -> bool` for own mons; for opponent, `revealed(opponent.active,
  "move_id") -> bool`.
- Selectors: `strongest_move against X` (argmax expected `damage_frac` median),
  `best bench by <expr over it>`, `exists bench b where <pred>`.

The predicate library lives in the Python runtime; the Rust compiler knows only
signatures (name, arity, types) from a shared `predicates.toml` so the two never drift.

### 4.5 Actions

- `use "move_id"` — compile-time checked against nothing (moves are team-dependent at
  runtime); runtime-checked for legality with fallback semantics per §4.1.
- `use strongest_move against <target>`.
- `use ... with tera` — terastallize this turn if available (runtime-checked).
- `switch_to <selector>`.

### 4.6 Deliberate semantic quirks (the steering payload)

These are correct-but-unfamiliar choices that steering must teach. They are the
measurement instrument: an agent that read the steering gets them right; an agent
pattern-matching from Pokémon knowledge on the internet gets them wrong in ways that
compile (Q2 excepted) and lose battles.

- **Q1: all HP and damage quantities are fractions** in [0,1]. There are no raw HP
  numbers anywhere in the language. `0.33` means a third of max HP.
- **Q2: type effectiveness is categorical**, not numeric. Writing `effectiveness(...) >
  2` is a type error (E032); the agent must use category comparisons like
  `effectiveness(m, d) at_least super`.
- **Q3: rule order is priority.** No scoring, no weights. Agents habitually try to write
  utility functions; the language refuses.
- **Q4: resolution operators are mandatory and non-redundant** (E030/E031 pair).

### 4.7 Grammar sketch

Anka-informed principles: one canonical form per construct, verbose keywords, named rules,
no operator symbols beyond comparisons. Keywords: `bot`, `format`, `on`, `turn`,
`forced_switch`, `rule`, `otherwise`, `when`, `do`, `and`, `or`, `not`, `exists`, `where`,
`use`, `switch_to`, `best`, `by`, `against`, `with`, `tera`, `likely`, `worst_case`,
`best_case`, `at_least`, `at_most`, `it`, `outspeeds`, `knows`. Comparisons: `=`, `!=`,
`<`, `<=`, `>`, `>=`. Comments: `# line`.

Full EBNF is a Claude Code task (M1), to be checked into `compiler/GRAMMAR.ebnf` and kept
authoritative.

## 5. Compiler requirements

Pipeline: lex → parse (with recovery: sync on `rule`/`otherwise`/block keywords, report
multiple errors per run) → name/scope check → type check (fact/est propagation) → emit.

**Diagnostics are a first-class output.** `riposte-c build bot.rpo` writes
`bot.policy.json` on success and always writes `bot.diag.json`:

```json
{
  "version": "0.1",
  "status": "error",
  "diagnostics": [
    {
      "code": "E030",
      "severity": "error",
      "span": {"file": "bot.rpo", "line": 7, "col": 10, "len": 34},
      "message": "condition has type tribool; `when` requires bool",
      "hint": "wrap in one of likely(...), worst_case(...), best_case(...)",
      "docs_tool": "explain_error:E030"
    }
  ]
}
```

Error code taxonomy (initial): E01x lexical, E02x name/scope/information-access (E020
unrevealed info), E03x types (E030 unresolved tribool, E031 redundant resolver, E032
categorical effectiveness misuse), E04x structure (E040 missing otherwise, E041 illegal
action for block), W1xx warnings (W100 unreachable rule: a later rule shadowed by an
earlier strictly-more-general one — best effort, syntactic subsumption only).

The `docs_tool` field is the hook that ties diagnostics to the MCP server: repair-loop
agents can call `explain_error("E030")` for a worked example. Human-facing pretty
rendering (miette-style) is nice-to-have, not required for evals.

**IR (policy.json)**: versioned, schema-validated by pydantic on load. Roughly: header
(name, format, source hash, compiler version), and for each block an ordered list of
`{rule_name, condition_ast, action}` with fully-resolved predicate calls (name + typed
args) in a small expression tree. No string re-parsing at runtime.

## 6. Runtime requirements

`RipostePlayer(Player)` loads a policy.json, and in `choose_move(battle)`:

1. Builds the state surface (§4.3) from the poke-env `Battle` object.
2. Determines block (`forced_switch` iff no moves available / after faint).
3. Evaluates rules top-down; predicate implementations in `predicates.py`.
4. Applies fallback semantics (§4.1) and logs per-turn traces: fired rule name, resolved
   condition values, chosen action, fallback events. Traces are JSONL per battle —
   these are the trajectory data for evals and the blog post.

Damage calc: implement gen 9 formula directly in Python against poke-env data
(base power, stats, STAB, type chart, boosts, burn, weather, screens; crits excluded from
estimates). Validate against a handful of hand-checked cases; exactness beyond that is not
required in v1 as long as it is deterministic and documented. Random battles are level-
variable; stat range estimation must use the actual level from battle state.

Determinism: eval battles seed the Showdown server PRNG (`--seed` per battle via the
sim's battle-stream options if available; otherwise record and replay seeds). One
turn-decision must be pure: same battle state → same action.

## 7. Eval harness

### 7.1 Task set

25-40 natural-language strategy briefs in `evals/tasks/`, e.g. "write a bot that keeps
hazards up and pivots out of bad matchups", "write a hyper-offense bot that terastallizes
early when it secures a KO", graded T1 (uses 3-5 language features) to T3 (needs bench
quantifiers, est resolution, both blocks). Each task has a golden reference program in
`evals/golden/` written by us, which doubles as the harness smoke test.

### 7.2 Conditions (the experiment)

- **C1 docs-dump**: full language reference (~Anka-style guide) in the prompt. One shot.
- **C2 progressive-MCP**: minimal seed prompt ("you are writing Riposte; discover the
  language via tools") + MCP server. Agent explores, then writes.
- **C3 docs + repair**: C1 plus up to R=3 repair rounds feeding back diag.json.
- **C4 MCP + repair**: C2 plus repair rounds; agent may call `explain_error`.

Models: at minimum one frontier and one small/cheap model (tiering is an existing
strength — reuse the pattern from a prior framework). k=5 samples per task per
condition per model.

### 7.3 Metrics

1. **compile pass@k** (k=1,5) per condition.
2. **Repair efficiency**: rounds to first successful compile; % never compiling.
3. **Win rate ground truth**: each compiled program plays N=200 battles per opponent
   against fixed baselines on the local server: `RandomPlayer`, `MaxDamagePlayer`
   (poke-env built-ins), `SimpleHeuristics` (our hand-written mid-tier), and the task's
   golden program. Report win rate with Wilson 95% CIs; N=200 gives ~±7% at p=0.5, which
   is enough to separate tiers — bump N only for close calls.
4. **Semantic quality deltas**: agent program win rate vs. golden program win rate on the
   same task (the "compiles but loses" gap — the headline metric).
5. **Quirk error profile**: frequency of E030/E031/E032/E040 per condition (does
   progressive discovery reduce quirk violations vs. docs dump?).
6. **Cost**: tokens per successful program per condition; battles are free, inference
   is not.
7. **Runtime fallback rate** from traces (proxy for legality-reasoning quality).

### 7.4 Harness mechanics

Python orchestrator: async battle execution (poke-env supports concurrent battles),
results in SQLite or parquet, analysis notebooks in `evals/analysis/`. Agent invocation
abstracted behind a driver interface so conditions can run against the Anthropic API
directly; MCP conditions run the agent with the riposte-mcp server attached. Pin model
versions in condition configs.

## 8. MCP server (riposte-mcp)

Progressive discovery is the point: the server exposes the language in grains, so the
agent's tool-selection machinery does the retrieval (same architectural insight as the
prior steering-docs-as-MCP-tools work, now measurable).

Tools (v1):

- `language_overview()` — one page: program shape, two blocks, the otherwise rule.
- `list_topics()` / `get_topic(name)` — grains: `types_and_estimates`, `state_surface`,
  `predicates`, `actions`, `selectors`, `quirks`, `worked_example_defensive`,
  `worked_example_offensive`.
- `predicate_reference(name)` — signature, semantics, one example each.
- `explain_error(code)` — cause + minimal broken/fixed pair.
- `check_program(source)` — runs riposte-c, returns diag.json. (This makes C2-without-
  repair still meaningfully interactive at write time; whether to allow it in C2 or only
  C4 is an experiment design decision — default: allowed in C4 only, so C2 measures
  discovery not iteration.)

The `steering/` directory is the single source of truth; both the C1 docs-dump document
and the MCP grains are generated from it so conditions differ in delivery, not content.

## 9. Milestones

**M0 — walking skeleton (first session).** Repo scaffold; local Showdown server cloned,
pinned, running with `--no-security`; two built-in poke-env players complete battles
headlessly; hand-written `policy.json` (no compiler) interpreted by a minimal
`RipostePlayer` that beats `RandomPlayer` >70% over 100 battles. This de-risks the entire
pipeline before any Rust exists. Also: pick the name (D-1), init the Rust workspace.

**M1 — compiler front end.** Lexer, parser with recovery, AST, GRAMMAR.ebnf,
diag.json rendering; compile the §4.1 example to IR with name checking only (types
stubbed). Golden parse-error snapshot tests.

**M2 — type system + predicates.** fact/est propagation, tribool + resolvers,
E020/E030/E031/E032/E040/E041; full predicate library in runtime incl. damage calc with
hand-checked validation cases; traces.

**M3 — eval harness v1.** Task briefs (first 15), golden programs, baselines incl.
SimpleHeuristics, battle orchestration with seeding, win-rate + CI analysis; run
C1 and C3 end to end on one model.

**M4 — MCP + full matrix.** riposte-mcp, steering grains, C2/C4, second model, full
metrics.

**M5 — blog post.** Eval learnings post drafted from harness results and traces (separate
outline session; the post is about evals, the DSL is the running example).

Sequencing note: M0 is strictly first and should be small. Do not start Rust before
battles run locally.

## 10. Open decisions

- **D-1 Name.** Riposte / Pivot / Parley / other. Check crates.io + PyPI + GitHub
  collisions before repo init.
- **D-2 `likely` semantics.** Median-of-range vs. threshold probability. v1: median,
  documented; revisit if it makes `likely` useless in practice.
- **D-3 Unknown items/abilities in damage calc.** v1 default: ignore unknowns (documented
  in steering as a known simplification) rather than widen ranges; revisit after M3 if
  golden-vs-agent gaps are dominated by it.
- **D-4 `check_program` availability in C2.** Default: C4 only (see §8).
- **D-5 W100 unreachable-rule warning scope.** Ship syntactic-subsumption-only or cut
  from v1 if it drags.

## 11. References

- poke-env docs: https://poke-env.readthedocs.io — Player API, Battle object, local
  server setup (`--no-security`).
- Showdown server: https://github.com/smogon/pokemon-showdown (pin commit in M0).
- Anka (design principles to reuse; framing to cite): arXiv:2512.23214.
- PokéLLMon: arXiv:2402.01118. PokéChamp: arXiv:2503.04094 (runtime-LLM contrast +
  eventual baseline tier).
- CangjieBench (unseen-language eval settings incl. agentic): arXiv:2603.14501.
