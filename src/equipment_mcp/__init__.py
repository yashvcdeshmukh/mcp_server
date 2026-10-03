"""IT equipment request MCP server and local ReAct agent."""


def main() -> None:
    from equipment_mcp.config import HOST, PATH, PORT
    from equipment_mcp.server import mcp

    mcp.run(
        transport="streamable-http",
        host=HOST,
        port=PORT,
        streamable_http_path=PATH,
    )
