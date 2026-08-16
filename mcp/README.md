# riposte-mcp — progressive language-discovery server

Serves the `steering/` single source of truth as MCP tools, so an agent discovers Riposte
grain by grain via its own tool-selection (SPEC §8). This is the **C2/C4** delivery channel;
the same content dumped into a prompt is **C1**.

## Tools

| Tool | Returns |
|------|---------|
| `language_overview()` | the one-page overview (program shape, blocks, otherwise) |
| `list_topics()` | the topic grains |
| `get_topic(name)` | one topic (`types_and_estimates`, `state_surface`, `predicates`, `actions`, `selectors`, `quirks`, `worked_example_*`) |
| `predicate_reference(name)` | signature (from `predicates.toml`) + semantics + example |
| `explain_error(code)` | a diagnostic's cause + minimal broken/fixed pair |
| `check_program(source)` | compiles with `riposte-c`, returns the `diag.json` report |

`check_program` needs the compiler built (`cargo build` in `compiler/`); it finds
`compiler/target/{release,debug}/riposte-c`, or honors `$RIPOSTE_C`.

## Run

```bash
pip install -e mcp/          # into the runtime venv
riposte-mcp                  # stdio transport
# or: python -m riposte_mcp.server
```

Register with an MCP client (stdio), e.g.:

```json
{
  "mcpServers": {
    "riposte": { "command": "riposte-mcp" }
  }
}
```

## Note on the experiment

Whether `check_program` is offered in C2 (discovery-only) or only C4 (discovery + repair) is
an eval-design decision (SPEC §8, D-4; default: C4 only). The tool exists here; the eval
harness decides which condition exposes it. Built on the MCP Python SDK 2.x (`MCPServer`).
