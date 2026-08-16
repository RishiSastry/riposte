"""Build the docs-dump reference (C1/C3 payload) from the same `steering/` single source the
MCP server serves — so conditions differ in *delivery*, not *content* (SPEC §8)."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STEERING = REPO / "steering"
PREDICATES_TOML = REPO / "predicates.toml"

# Pedagogical order for the topic grains.
_TOPIC_ORDER = [
    "types_and_estimates",
    "state_surface",
    "predicates",
    "actions",
    "selectors",
    "quirks",
    "worked_example_defensive",
    "worked_example_offensive",
]


def _predicate_reference() -> str:
    data = tomllib.loads(PREDICATES_TOML.read_text())
    lines = ["# Predicate reference (signatures)\n"]
    for name, e in sorted(data["predicates"].items()):
        params = ", ".join(e["params"])
        infix = "  [infix]" if e.get("infix") else ""
        lines.append(f"- `{name}({params}) -> {e['ret']}`{infix} — {e.get('doc', '').strip()}")
    return "\n".join(lines)


def steering_docs() -> str:
    """The full language reference as one string (overview + topics + predicate signatures +
    error explanations)."""
    parts = [(STEERING / "overview.md").read_text()]
    for topic in _TOPIC_ORDER:
        p = STEERING / "topics" / f"{topic}.md"
        if p.exists():
            parts.append(p.read_text())
    parts.append(_predicate_reference())
    parts.append("# Compiler errors\n")
    for err in sorted((STEERING / "errors").glob("E*.md")):
        parts.append(err.read_text())
    return "\n\n---\n\n".join(parts)


if __name__ == "__main__":
    docs = steering_docs()
    print(f"[steering_docs] {len(docs)} chars, ~{len(docs)//4} tokens")
