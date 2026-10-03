"""Mock employees and role policies."""

from datetime import date, timedelta
from typing import TypedDict


class Unit(TypedDict):
    item: str
    acquired_on: str


class Employee(TypedDict):
    employee_id: str
    name: str
    role: str
    start_date: str
    equipment: list[Unit]


class PolicyRow(TypedDict):
    role: str
    item: str
    maximum: int
    interval_years: int


POLICY: list[PolicyRow] = [
    {"role": "standard", "item": "laptop", "maximum": 1, "interval_years": 4},
    {"role": "standard", "item": "monitor", "maximum": 1, "interval_years": 3},
    {"role": "standard", "item": "headset", "maximum": 1, "interval_years": 2},
    {"role": "manager", "item": "laptop", "maximum": 1, "interval_years": 2},
    {"role": "manager", "item": "monitor", "maximum": 2, "interval_years": 3},
    {"role": "manager", "item": "headset", "maximum": 1, "interval_years": 2},
]


def add_years(day: date, years: int) -> date:
    """Move a date by calendar years. A missing day becomes the next day that exists."""
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return date(day.year + years, 3, 1)


def _on(years_ago: int, days: int) -> str:
    """ISO date `years_ago` before today, shifted by `days` (negative is earlier)."""
    return (add_years(date.today(), -years_ago) + timedelta(days=days)).isoformat()


def _person(
    employee_id: str,
    name: str,
    role: str,
    equipment: list[Unit],
) -> Employee:
    return {
        "employee_id": employee_id,
        "name": name,
        "role": role,
        "start_date": _on(2, 0),
        "equipment": equipment,
    }


EMPLOYEES: dict[str, Employee] = {
    "e001": _person(
        "e001",
        "Avery Chen",
        "standard",
        [{"item": "laptop", "acquired_on": _on(1, 0)}],
    ),
    "e002": _person(
        "e002",
        "Mina Patel",
        "standard",
        [{"item": "monitor", "acquired_on": _on(3, -30)}],
    ),
    "e003": _person(
        "e003",
        "Luis Ortega",
        "standard",
        [
            {"item": "laptop", "acquired_on": _on(4, 30)},
            {"item": "headset", "acquired_on": ""},
        ],
    ),
    "e004": _person("e004", "Sam Okonkwo", "standard", []),
    "e005": _person(
        "e005",
        "Priya Shah",
        "standard",
        [
            {"item": "laptop", "acquired_on": _on(2, 0)},
            {"item": "laptop", "acquired_on": _on(1, 0)},
        ],
    ),
    "e006": _person(
        "e006",
        "Noah Berg",
        "standard",
        [{"item": "laptop", "acquired_on": ""}],
    ),
    "e007": _person(
        "e007",
        "Elena Rossi",
        "standard",
        [{"item": "laptop", "acquired_on": "not-a-date"}],
    ),
    "e008": _person(
        "e008",
        "Chris Adeyemi",
        "standard",
        [{"item": "laptop", "acquired_on": _on(0, 30)}],
    ),
    "e009": _person(
        "e009",
        "Jordan Blake",
        "manager",
        [{"item": "laptop", "acquired_on": _on(2, 30)}],
    ),
    "e010": _person(
        "e010",
        "Riley Nguyen",
        "manager",
        [
            {"item": "monitor", "acquired_on": _on(3, -30)},
            {"item": "monitor", "acquired_on": _on(3, -30)},
        ],
    ),
    "e011": _person(
        "e011",
        "Alex Kim",
        "contractor",
        [{"item": "laptop", "acquired_on": _on(1, 0)}],
    ),
    "e012": _person(
        "e012",
        "Morgan Lee",
        "manager",
        [{"item": "monitor", "acquired_on": _on(1, 0)}],
    ),
    "e013": _person(
        "e013",
        "Taylor Brooks",
        "standard",
        [{"item": "laptop", "acquired_on": _on(4, 0)}],
    ),
}
