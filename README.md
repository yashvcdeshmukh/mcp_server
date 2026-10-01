# equipment-mcp

MCP server and local agent for internal IT equipment requests. The agent uses Ollama on this machine (`qwen3:8b`, thinking on). It does not call a cloud model.

## Layout

- `src/equipment_mcp/data.py` — mock employees and policies
- `src/equipment_mcp/tools.py` — plain functions, covered by unit tests
- `src/equipment_mcp/server.py` — MCP tool wrappers
- `src/equipment_mcp/agent.py` — ReAct loop against the local model
- `docs/requirements.md` — request fields and policy rules
- `scripts/smoke_client.py` — one-tool client connectivity check

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync --all-groups
uv run pytest
```

Ollama stays on the host and should already be serving `qwen3:8b`. Inside the dev container, `OLLAMA_HOST` points at `http://host.docker.internal:11434`.
