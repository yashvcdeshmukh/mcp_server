"""Connectivity check against an already running equipment-mcp server."""

import logging

import anyio
from mcp import Client

from equipment_mcp.config import MCP_URL

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)


async def main() -> None:
    async with Client(MCP_URL) as client:
        listed = await client.list_tools()
        print([tool.name for tool in listed.tools])
        result = await client.call_tool(
            "get_employee_info",
            {"employee_id": "E001"},
        )
        print(result)
        print(result.is_error)
        print(result.structured_content)
        limits = await client.call_tool("get_policy_limits", {"role": "standard"})
        print(limits.structured_content)
        eligibility = await client.call_tool(
            "check_request_eligibility",
            {"employee_id": "E001", "item": "laptop"},
        )
        print(eligibility.structured_content)
        flagged = await client.call_tool(
            "flag_for_human_review",
            {
                "employee_id": "E001",
                "request": {"item": "laptop", "reason": "smoke"},
                "basis": "smoke check",
            },
        )
        print(flagged.structured_content)


if __name__ == "__main__":
    anyio.run(main)
