"""MCP client for the servers the agent can call."""

import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

from mcp.client.session_group import ClientSessionGroup, StreamableHttpParameters

from equipment_mcp.config import MCP_URL

SERVERS = {"equipment": MCP_URL}


def _require_server(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    try:
        with socket.create_connection((host, port), timeout=1):
            return
    except OSError:
        raise SystemExit(
            f"The equipment server is not running at {url}. Start it with: uv run equipment-mcp"
        ) from None


@asynccontextmanager
async def connect() -> AsyncIterator[ClientSessionGroup]:
    """Connect to every server in SERVERS. A second entry is another server."""
    for url in SERVERS.values():
        _require_server(url)
    group: ClientSessionGroup

    def name(tool_name: str, _server_info: object) -> str:
        if tool_name in group.tools:
            return f"{server}.{tool_name}"
        return tool_name

    group = ClientSessionGroup(component_name_hook=name)
    async with group:
        for server, url in SERVERS.items():
            await group.connect_to_server(StreamableHttpParameters(url=url))
        yield group


def tool_list(group: ClientSessionGroup) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": tool.description or "",
            "input_schema": tool.input_schema,
        }
        for name, tool in group.tools.items()
    ]


def _text(result: Any) -> str:
    parts = []
    for block in getattr(result, "content", None) or []:
        piece = getattr(block, "text", None)
        if piece:
            parts.append(piece)
    return "\n".join(parts)


async def call_tool(
    group: ClientSessionGroup,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    try:
        result = await group.call_tool(name, arguments)
    except Exception as exc:
        return {"tool": name, "error": str(exc), "content": str(exc)}
    return {
        "tool": name,
        "is_error": result.is_error,
        "structured": result.structured_content,
        "content": _text(result),
    }
