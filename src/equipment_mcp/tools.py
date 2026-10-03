"""Plain request-handler functions. MCP wrappers live in server.py."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from equipment_mcp.data import EMPLOYEES, POLICY, add_years

REVIEWS = Path("reviews/escalations.jsonl")


def _key(value: str) -> str:
    return value.strip().lower()


def _completed_years(start: date, today: date) -> int:
    years = today.year - start.year
    if add_years(start, years) > today:
        years -= 1
    return max(years, 0)


def get_employee_info(employee_id: str) -> dict[str, Any]:
    """Return the employee record for an id, plus tenure in completed years."""
    key = _key(employee_id)
    record = EMPLOYEES.get(key)
    if record is None:
        return {"code": "employee_not_found", "employee_id": key}
    start = date.fromisoformat(record["start_date"])
    return {
        **record,
        "equipment": list(record["equipment"]),
        "tenure_years": _completed_years(start, date.today()),
    }


def get_policy_limits(role: str) -> dict[str, Any]:
    key = _key(role)
    rows = [dict(row) for row in POLICY if row["role"] == key]
    if not rows:
        return {"code": "unknown_role", "role": key, "limits": []}
    return {"role": key, "limits": rows}


def _eligibility(
    employee_id: str,
    item: str,
    result: str,
    cause: str | None,
    anniversary: str | None,
) -> dict[str, str | None]:
    return {
        "employee_id": employee_id,
        "item": item,
        "result": result,
        "cause": cause,
        "anniversary": anniversary,
    }


def check_request_eligibility(employee_id: str, item: str) -> dict[str, str | None]:
    """Return whether one item is inside the role's limit. Does not read a reason."""
    today = date.today()
    key = _key(employee_id)
    name = _key(item)
    record = EMPLOYEES.get(key)
    if record is None:
        return _eligibility(key, name, "undetermined", "employee_not_found", None)

    limits = get_policy_limits(record["role"])
    if limits.get("code") == "unknown_role":
        return _eligibility(key, name, "undetermined", "role_not_in_policy", None)
    row = next((entry for entry in limits["limits"] if entry["item"] == name), None)
    if row is None:
        return _eligibility(key, name, "undetermined", "no_policy_row", None)

    units = [unit for unit in record["equipment"] if _key(unit["item"]) == name]
    acquired: list[date] = []
    for unit in units:
        raw = unit["acquired_on"].strip()
        if not raw:
            return _eligibility(key, name, "undetermined", "acquired_date_missing", None)
        try:
            parsed = date.fromisoformat(raw)
        except ValueError:
            return _eligibility(key, name, "undetermined", "acquired_date_unreadable", None)
        if parsed > today:
            return _eligibility(key, name, "undetermined", "acquired_date_in_future", None)
        acquired.append(parsed)

    maximum = row["maximum"]
    interval = row["interval_years"]
    count = len(acquired)
    if count > maximum:
        oldest = min(acquired)
        return _eligibility(
            key,
            name,
            "undetermined",
            "count_above_maximum",
            add_years(oldest, interval).isoformat(),
        )
    if count < maximum:
        anniversary = add_years(min(acquired), interval).isoformat() if acquired else None
        return _eligibility(key, name, "eligible", None, anniversary)

    if not acquired:
        return _eligibility(key, name, "ineligible", None, None)

    anniversary_on = add_years(min(acquired), interval)
    result = "eligible" if anniversary_on <= today else "ineligible"
    return _eligibility(key, name, result, None, anniversary_on.isoformat())


def flag_for_human_review(
    employee_id: str,
    request: dict[str, str],
    basis: str,
) -> dict[str, Any]:
    """Append an escalation. Does not change the employee record."""
    record = {
        "recorded_at": datetime.now().astimezone().isoformat(),
        "employee_id": _key(employee_id),
        "request": {"item": request["item"], "reason": request["reason"]},
        "basis": basis,
    }
    REVIEWS.parent.mkdir(parents=True, exist_ok=True)
    with REVIEWS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return record
