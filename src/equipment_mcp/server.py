"""MCP server that exposes the equipment-request tools."""

from mcp.server import MCPServer
from equipment_mcp.tools import get_employee_info

mcp = MCPServer("equipment-mcp")
mcp.tool()(get_employee_info)
