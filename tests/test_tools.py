from equipment_mcp.tools import get_employee_info
from equipment_mcp.data import EMPLOYEES

def test_get_employee_info() -> None:
    assert get_employee_info("E001") == EMPLOYEES["E001"]

