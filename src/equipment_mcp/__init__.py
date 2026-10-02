"""IT equipment request MCP server and local ReAct agent."""
from equipment_mcp.server import mcp


def main() -> None:
    """Run the MCP server."""
    mcp.run()
