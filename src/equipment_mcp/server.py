"""MCP server that exposes the equipment-request tools."""

from mcp.server import MCPServer

from equipment_mcp.tools import (
    check_request_eligibility,
    flag_for_human_review,
    get_employee_info,
    get_policy_limits,
)

mcp = MCPServer("equipment-mcp")
mcp.tool()(get_employee_info)
mcp.tool()(get_policy_limits)
mcp.tool()(check_request_eligibility)
mcp.tool()(flag_for_human_review)
