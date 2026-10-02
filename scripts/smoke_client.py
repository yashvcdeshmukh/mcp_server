"""One-tool MCP client check."""

import anyio
from mcp import Client
from mcp.client.stdio import StdioServerParameters


async  def main() -> None:
    """Run the smoke client."""
    server = StdioServerParameters(command="uv", args=["run", "equipment-mcp"])
    async with Client(server) as client:
        listed = await client.list_tools()
        print([tool.name for tool in listed.tools])
        result = await client.call_tool(
            "get_employee_info",
            {"employee_id": "E001"},
        )
        print(result)
        print(result.is_error)
        print(result.structured_content)


if __name__ == "__main__":
    anyio.run(main)
