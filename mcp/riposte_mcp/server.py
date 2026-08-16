"""riposte-mcp — progressive language-discovery server (SPEC §8).

Exposes the `steering/` single source of truth as MCP tools so an agent's own
tool-selection machinery does the retrieval, grain by grain. The tool *logic* lives in plain
module-level functions (unit-testable without an MCP client); `main()` registers them with
FastMCP and runs over stdio.

Tools: language_overview · list_topics · get_topic · predicate_reference · explain_error ·
check_program.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STEERING = REPO_ROOT / "steering"
TOPICS = STEERING / "topics"
ERRORS = STEERING / "errors"
PREDICATES_TOML = REPO_ROOT / "predicates.toml"

# One canned usage example per predicate for predicate_reference (signatures come from the
# toml; these show idiomatic use, including the resolver where the return is a tribool).
_EXAMPLES = {
    "can_ko": "when likely(can_ko(my.active, opponent.active))",
    "guaranteed_ko": "when worst_case(guaranteed_ko(opponent.active, my.active))",
    "outspeeds": "when worst_case(opponent.active outspeeds my.active)",
    "effectiveness": "when effectiveness(opponent.active.primary_type, my.active) at_least super",
    "resists": "when exists bench b where resists(b, opponent.active.primary_type)",
    "is_immune": "when is_immune(my.active, opponent.active.primary_type)",
    "matchup_score": "do switch_to best bench by matchup_score(it, opponent.active)",
    "hp_fraction": "do switch_to best bench by hp_fraction(it)",
    "knows": 'when my.active knows "stealthrock"',
    "revealed": 'when revealed(opponent.active, "earthquake")',
    "has_hazard": "when not opponent.side.has_hazard(stealth_rock)",
    "hazard_layers": "when hazard_layers(my.side, spikes) < 2",
    "has_screen": "when has_screen(opponent.side, reflect)",
    "damage_frac": "when likely(guaranteed_ko(my.active, opponent.active))  # (damage_frac is the underlying est frac)",
    "hazard_damage_on_switch": "when hazard_damage_on_switch(my.active) < 0.25",
}


# ─────────────────────────── tool implementations ───────────────────────────


def language_overview() -> str:
    """One page: the shape of a Riposte program, the two blocks, and the mandatory otherwise
    rule. Start here."""
    return (STEERING / "overview.md").read_text()


def list_topics() -> list[str]:
    """List the discoverable steering topics (grains). Pass one to get_topic."""
    return sorted(p.stem for p in TOPICS.glob("*.md"))


def get_topic(name: str) -> str:
    """Return a steering topic by name (e.g. 'types_and_estimates', 'quirks'). Use
    list_topics() to see the options."""
    path = TOPICS / f"{name}.md"
    if not path.exists():
        return f"No topic '{name}'. Available: {', '.join(list_topics())}"
    return path.read_text()


def predicate_reference(name: str) -> str:
    """Signature, epistemic return kind, semantics, and an example for one predicate."""
    data = tomllib.loads(PREDICATES_TOML.read_text())
    preds = data["predicates"]
    entry = preds.get(name)
    if entry is None:
        return f"No predicate '{name}'. Known: {', '.join(sorted(preds))}"
    params = ", ".join(entry["params"])
    infix = "   [infix]" if entry.get("infix") else ""
    lines = [
        f"{name}({params}) -> {entry['ret']}{infix}",
        "",
        entry.get("doc", ""),
    ]
    if name in _EXAMPLES:
        lines += ["", f"Example: {_EXAMPLES[name]}"]
    return "\n".join(lines)


def explain_error(code: str) -> str:
    """Explain a compiler diagnostic code (e.g. 'E030') with a minimal broken/fixed pair."""
    code = code.strip().upper()
    if not code.startswith("E") and not code.startswith("W"):
        code = "E" + code
    path = ERRORS / f"{code}.md"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in ERRORS.glob("*.md")))
        return f"No explanation for '{code}'. Available: {available}"
    return path.read_text()


def _find_compiler() -> Path | None:
    if env := os.environ.get("RIPOSTE_C"):
        p = Path(env)
        return p if p.exists() else None
    for build in ("release", "debug"):
        cand = REPO_ROOT / "compiler" / "target" / build / "riposte-c"
        if cand.exists():
            return cand
    return None


def check_program(source: str) -> dict:
    """Compile Riposte source with riposte-c and return the diag.json report (status +
    diagnostics). Use this to check a program before finalizing it."""
    compiler = _find_compiler()
    if compiler is None:
        return {
            "status": "error",
            "error": "riposte-c not built. Run `cargo build` in compiler/, or set RIPOSTE_C.",
        }
    with tempfile.TemporaryDirectory() as tmp:
        src_path = Path(tmp) / "bot.rpo"
        src_path.write_text(source)
        subprocess.run(
            [str(compiler), "build", str(src_path), "--out-dir", tmp],
            capture_output=True,
            text=True,
        )
        diag_path = Path(tmp) / "bot.diag.json"
        if not diag_path.exists():
            return {"status": "error", "error": "compiler produced no diag.json"}
        return json.loads(diag_path.read_text())


# ─────────────────────────────── MCP wiring ────────────────────────────────

TOOLS = [
    language_overview,
    list_topics,
    get_topic,
    predicate_reference,
    explain_error,
    check_program,
]


def build_server():
    """Construct the MCP server (SDK 2.x) with all tools registered."""
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(
        "riposte",
        instructions=(
            "Riposte is a DSL for Pokémon battle policies you have never seen. Discover it "
            "with these tools: start with language_overview(), then list_topics()/get_topic(), "
            "predicate_reference(name) for signatures, explain_error(code) when the compiler "
            "rejects your program, and check_program(source) to compile and see diagnostics."
        ),
    )
    for fn in TOOLS:
        server.add_tool(fn)
    return server


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
