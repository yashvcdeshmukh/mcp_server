"""Plain request-handler functions. MCP wrappers live in server.py."""

from typing import Any
from equipment_mcp.data import EMPLOYEES

def get_employee_info(employee_id: str) -> dict[str, Any]:
    """Return the employee record for an id."""
    key = employee_id.strip()
    record = EMPLOYEES.get(key)
    if record is None:
        return {"code": "employee_not_found", "employee_id": key}
    return record