"""DeepAgentsDriver — the real agent driver (LangChain `deepagents` + MCP).

Spawns the MCP server executable over stdio, loads its tools via langchain-mcp-adapters,
builds a deep agent (Claude by default), runs it on a brief, and extracts the program it
wrote. The steering `Condition` gates which MCP tools the agent sees (e.g. `check_program`
only under a repair condition, D-4) and how many repair rounds it may take.

Heavy deps live behind the `evalkit[agent]` extra and are imported lazily, so evalkit's core
(parser, runner, stub driver, CLI) installs and tests without LangChain. Running this driver
needs `pip install evalkit[agent]` and an Anthropic credential (ANTHROPIC_API_KEY or an
`ant auth login` profile).
"""

from __future__ import annotations

import re

from .driver import Artifact, Condition

# Model tiers (SPEC §7.2). Frontier + cheap; both Claude by default, overridable via --model.
FRONTIER_MODEL = "claude-opus-4-8"
CHEAP_MODEL = "claude-haiku-4-5"

_SEED_INSTRUCTIONS = """\
You are writing a program in **Riposte**, a small declarative language for Pokémon battle
policies that you have never seen before. You must DISCOVER the language using the tools
available to you before writing — do not guess its syntax from other languages or from
Pokémon knowledge.

Suggested process:
1. Call `language_overview()` to learn the program shape (the two blocks and the mandatory
   `otherwise` rule).
2. Use `list_topics()` / `get_topic(name)` and `predicate_reference(name)` to learn the type
   system (facts vs estimates, tribool + resolvers), the state surface, predicates, actions,
   selectors, and especially the deliberate quirks.
3. Write a complete, valid Riposte program that satisfies the task.
{repair_clause}
When you are done, output your FINAL program as a single fenced code block tagged `rpo`:

```rpo
bot "..." format gen9randombattle
...
```

Output nothing after the final code block.
"""

_REPAIR_CLAUSE = (
    "4. Call `check_program(source)` to compile it. If it returns diagnostics, call "
    "`explain_error(code)` for any code you don't understand and fix the program. Repeat "
    "until it compiles cleanly or you have made {n} repair attempts.\n"
)

_FENCE_RE = re.compile(r"```(?:rpo|riposte)?\s*\n(.*?)```", re.DOTALL)


class DeepAgentsDriver:
    def __init__(self, mcp_cmd: list[str] | None, model: str = FRONTIER_MODEL):
        if not mcp_cmd:
            raise ValueError(
                "DeepAgentsDriver requires --mcp-cmd (the MCP server executable, e.g. riposte-mcp)"
            )
        self._mcp_cmd = mcp_cmd
        self._model = model

    async def write_program(self, brief: str, condition: Condition) -> Artifact:
        # lazy heavy imports (evalkit[agent])
        from deepagents import create_deep_agent
        from langchain_anthropic import ChatAnthropic
        from langchain_mcp_adapters.client import MultiServerMCPClient

        servers = {
            "riposte": {
                "command": self._mcp_cmd[0],
                "args": list(self._mcp_cmd[1:]),
                "transport": "stdio",
            }
        }
        client = MultiServerMCPClient(servers)
        tools = await client.get_tools()

        # Condition gates check_program exposure (D-4: repair conditions only).
        if not condition.allow_check_program:
            tools = [t for t in tools if getattr(t, "name", "") != "check_program"]

        repair_clause = ""
        if condition.allow_check_program and condition.max_repair_rounds > 0:
            repair_clause = _REPAIR_CLAUSE.format(n=condition.max_repair_rounds)
        instructions = _SEED_INSTRUCTIONS.format(repair_clause=repair_clause)

        model = ChatAnthropic(model=self._model, max_tokens=8000)
        agent = create_deep_agent(tools=tools, model=model, instructions=instructions)
        result = await agent.ainvoke({"messages": [{"role": "user", "content": brief}]})

        messages = result.get("messages", []) if isinstance(result, dict) else []
        text = _final_text(messages)
        source = _extract_program(text)
        rounds = _count_tool_calls(messages, "check_program")
        return Artifact(
            source=source,
            repair_rounds=rounds,
            transcript=messages,
            meta={"driver": "deepagents", "model": self._model, "condition": condition.name},
        )


def _final_text(messages: list) -> str:
    """Text of the last AI message (content may be a string or a list of blocks)."""
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content")
        if not content:
            continue
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [b.get("text", "") if isinstance(b, dict) else str(b) for b in content]
            joined = "".join(parts).strip()
            if joined:
                return joined
    return ""


def _extract_program(text: str) -> str:
    """The last fenced ```rpo block, or the raw text if the agent didn't fence it."""
    blocks = _FENCE_RE.findall(text)
    if blocks:
        return blocks[-1].strip() + "\n"
    return text.strip() + "\n"


def _count_tool_calls(messages: list, name: str) -> int:
    n = 0
    for msg in messages:
        for call in getattr(msg, "tool_calls", None) or []:
            if (call.get("name") if isinstance(call, dict) else getattr(call, "name", "")) == name:
                n += 1
    return n
