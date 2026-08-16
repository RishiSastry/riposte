# steering — single source of truth for how to write Riposte

This directory is the **one** place the language is taught. Both delivery channels in the
experiment derive from it, so conditions differ in *delivery*, not *content* (SPEC §8):

- **C1 docs-dump** — the files here, concatenated into one reference document in the prompt.
- **C2/C4 progressive-MCP** — the `riposte-mcp` server serves these as discoverable grains.

## Layout

```
steering/
├── overview.md              # language_overview(): program shape, blocks, otherwise
├── topics/                  # get_topic(name) grains
│   ├── types_and_estimates.md   # fact/est, tribool, resolvers  ← the core idea
│   ├── state_surface.md         # what you can read (fact vs est)
│   ├── predicates.md            # the predicate library (detail via predicate_reference)
│   ├── actions.md               # use / use strongest_move / switch_to
│   ├── selectors.md             # strongest_move, best…by, exists…where, `it`
│   ├── quirks.md                # Q1 fractions, Q2 categorical eff, Q3 order, Q4 resolvers
│   ├── worked_example_defensive.md
│   └── worked_example_offensive.md
└── errors/                  # explain_error(code): cause + broken/fixed pair
    └── E0xx.md
```

## Sources that stay authoritative elsewhere

- **Predicate signatures** come from `predicates.toml` (repo root), not duplicated here —
  `predicate_reference(name)` combines the toml signature with the `predicates` topic.
- **Grammar** is `compiler/GRAMMAR.ebnf`.

Keep prose here consistent with those two files; when they change, update the topics.
