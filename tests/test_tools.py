import json
from copy import deepcopy
from datetime import date

from equipment_mcp.data import EMPLOYEES, POLICY, add_years
from equipment_mcp.tools import (
    REVIEWS,
    _completed_years,
    check_request_eligibility,
    flag_for_human_review,
    get_employee_info,
    get_policy_limits,
)


def _anniversary(employee_id: str, item: str) -> str:
    acquired = date.fromisoformat(EMPLOYEES[employee_id]["equipment"][0]["acquired_on"])
    limits = get_policy_limits(EMPLOYEES[employee_id]["role"])
    interval = next(row["interval_years"] for row in limits["limits"] if row["item"] == item)
    return add_years(acquired, interval).isoformat()


def test_known_employee_is_a_copy_with_tenure() -> None:
    found = get_employee_info("E001")
    stored = EMPLOYEES["e001"]
    assert found["employee_id"] == "e001"
    assert found["name"] == stored["name"]
    assert found["role"] == stored["role"]
    assert found["start_date"] == stored["start_date"]
    assert found["equipment"] == stored["equipment"]
    original_equipment = list(stored["equipment"])
    found["equipment"].append({"item": "headset", "acquired_on": "2020-01-01"})
    assert stored["equipment"] == original_equipment
    assert "tenure_years" not in stored
    start = date.fromisoformat(stored["start_date"])
    assert found["tenure_years"] == _completed_years(start, date.today())


def test_unknown_employee() -> None:
    assert get_employee_info("  Missing ") == {
        "code": "employee_not_found",
        "employee_id": "missing",
    }


def test_policy_limits_normalize_role() -> None:
    limits = get_policy_limits(" Standard ")
    assert limits["role"] == "standard"
    assert limits["limits"] == [row for row in POLICY if row["role"] == "standard"]


def test_unknown_role() -> None:
    assert get_policy_limits("intern") == {
        "code": "unknown_role",
        "role": "intern",
        "limits": [],
    }


def test_manager_limits() -> None:
    limits = get_policy_limits("manager")
    by_item = {row["item"]: row for row in limits["limits"]}
    assert by_item["laptop"]["interval_years"] == 2
    assert by_item["monitor"]["maximum"] == 2
    assert by_item["headset"]["interval_years"] == 2


def test_eligibility_rows() -> None:
    assert check_request_eligibility("nobody", "laptop")["cause"] == "employee_not_found"
    assert check_request_eligibility("e011", "laptop")["cause"] == "role_not_in_policy"

    tablet = check_request_eligibility("e001", "drawing tablet")
    assert tablet["result"] == "undetermined"
    assert tablet["cause"] == "no_policy_row"
    assert tablet["anniversary"] is None

    missing = check_request_eligibility("e006", "laptop")
    assert missing["cause"] == "acquired_date_missing"
    assert missing["anniversary"] is None

    unreadable = check_request_eligibility("e007", "laptop")
    assert unreadable["cause"] == "acquired_date_unreadable"
    assert unreadable["anniversary"] is None

    future = check_request_eligibility("e008", "laptop")
    assert future["cause"] == "acquired_date_in_future"
    assert future["anniversary"] is None

    over = check_request_eligibility("e005", "laptop")
    assert over["result"] == "undetermined"
    assert over["cause"] == "count_above_maximum"
    assert over["anniversary"] == _anniversary("e005", "laptop")

    none = check_request_eligibility("e004", "laptop")
    assert none["result"] == "eligible"
    assert none["cause"] is None
    assert none["anniversary"] is None

    due = check_request_eligibility(" E002 ", "Monitor")
    assert due["result"] == "eligible"
    assert due["cause"] is None
    assert due["item"] == "monitor"
    assert due["anniversary"] == _anniversary("e002", "monitor")

    early = check_request_eligibility("e003", "laptop")
    assert early["result"] == "ineligible"
    manager_laptop = check_request_eligibility("e009", "laptop")
    assert manager_laptop["result"] == "ineligible"
    assert early["cause"] is None
    assert early["anniversary"] == _anniversary("e003", "laptop")

    tied = check_request_eligibility("e010", "monitor")
    assert tied["result"] == "eligible"
    assert tied["anniversary"] == _anniversary("e010", "monitor")

    under_cap = check_request_eligibility("e012", " monitor ")
    assert under_cap == {
        "employee_id": "e012",
        "item": "monitor",
        "result": "eligible",
        "cause": None,
        "anniversary": _anniversary("e012", "monitor"),
    }

    on_anniversary = check_request_eligibility("e013", "laptop")
    assert on_anniversary["result"] == "eligible"
    assert on_anniversary["anniversary"] == date.today().isoformat()

    other_item = check_request_eligibility("e003", "headset")
    assert other_item["cause"] == "acquired_date_missing"
    assert early["result"] == "ineligible"

    assert manager_laptop["anniversary"] == _anniversary("e009", "laptop")
    assert set(manager_laptop) == {"employee_id", "item", "result", "cause", "anniversary"}


def test_feb_29_moves_to_the_next_existing_day() -> None:
    assert add_years(date(2024, 2, 29), 1) == date(2025, 3, 1)
    assert add_years(date(2024, 2, 29), 4) == date(2028, 2, 29)


def test_tenure_counts_completed_anniversaries() -> None:
    assert _completed_years(date(2020, 6, 15), date(2021, 6, 15)) == 1
    assert _completed_years(date(2020, 6, 15), date(2021, 6, 14)) == 0
    assert _completed_years(date(2024, 2, 29), date(2025, 2, 28)) == 0
    assert _completed_years(date(2024, 2, 29), date(2025, 3, 1)) == 1


def test_first_bad_date_wins_and_maximum_zero_is_ineligible() -> None:
    person = EMPLOYEES["e004"]
    original = person["equipment"]
    person["equipment"] = [
        {"item": "laptop", "acquired_on": ""},
        {"item": "laptop", "acquired_on": "not-a-date"},
    ]
    POLICY.append({"role": "standard", "item": "tablet", "maximum": 0, "interval_years": 1})
    try:
        assert check_request_eligibility("e004", "laptop")["cause"] == "acquired_date_missing"
        blocked = check_request_eligibility("e004", "tablet")
        assert blocked["result"] == "ineligible"
        assert blocked["cause"] is None
        assert blocked["anniversary"] is None
    finally:
        person["equipment"] = original
        POLICY.pop()


def test_flag_records_without_changing_employees() -> None:
    before = deepcopy(EMPLOYEES)
    recorded = flag_for_human_review(
        "E001",
        {"item": "Laptop", "reason": "Because I asked"},
        "unit test",
    )
    assert EMPLOYEES == before
    assert recorded["employee_id"] == "e001"
    assert recorded["request"] == {"item": "Laptop", "reason": "Because I asked"}
    assert recorded["basis"] == "unit test"
    assert "result" not in recorded
    lines = REVIEWS.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[-1])["basis"] == "unit test"
    again = flag_for_human_review(
        "missing",
        {"item": "laptop", "reason": "  still asking  "},
        "unit test again",
    )
    assert again["employee_id"] == "missing"
    assert again["request"]["reason"] == "  still asking  "
    assert EMPLOYEES == before
    lines = REVIEWS.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[-1])["basis"] == "unit test again"
    assert json.loads(lines[-2])["basis"] == "unit test"
