# Equipment requests

An employee asks for one piece of equipment. The handler looks up who they are, checks that role's limits against what they already have, and approves, denies, or escalates.

Today is the calendar date in the local timezone of the process that runs eligibility. It is read once at the start of the decision and reused for the draft. Two steps in one decision must not see two dates.

The handler does not edit the equipment file. An approval means a person may issue or replace a unit later. The next request still sees the file as it is.

If the facts or the reason are not enough to approve or deny, the handler escalates. It does not guess, and it does not invent a limit.

## Request

A request has an `employee_id`, one `item`, and a `reason`.

The catalog is whatever appears in the policy table below. There is no second list of item names. A role and item with no row are outside the policy.

`get_employee_info` returns the name, the role, the hire date, and the equipment on file. Each unit has an item and the date it was acquired. The hire date is there so a reviewer has context. It is not an input to eligibility, so the implementation cannot grow a seniority rule by accident.

`get_policy_limits` returns that role's rows from the table.

## Policy

The table is the only policy data. The eligibility check looks up one row and applies the same test to every role and item. It does not branch on a particular name.

| Role | Item | Maximum | Interval |
|---|---|---|---|
| standard | laptop | 1 | 4 years |
| standard | monitor | 1 | 3 years |
| standard | headset | 1 | 2 years |
| manager | laptop | 1 | 2 years |
| manager | monitor | 2 | 3 years |
| manager | headset | 1 | 2 years |

A person may hold up to the maximum. One request moves one unit. A replacement swaps the oldest unit, so the holding stays at the maximum. It does not add a unit on top.

The oldest unit is the one replaced because every unit of an item shares one interval, and the oldest reaches that interval first. Units that share the earliest date are the same age. The draft cites that date.

A unit is due on its anniversary: the acquired date plus the interval, in calendar years. If that day does not exist, the anniversary is the next day that does. The interval is never shortened. The unit is due when today is on that anniversary or after it.

## Eligibility

`check_request_eligibility(employee_id, item)` does not read the reason. The same employee and item must always produce the same result, and every judgement about the wording stays in the decision below.

It returns three things: the result, the cause when the result is undetermined, and the anniversary of the oldest unit when that unit exists. The agent cites those values. It does not compute the anniversary itself. The calendar rule lives in the tool, so the date in the draft is the same date that produced the result.

The count is the number of units of the submitted item. The maximum and the interval come from that item's row. A count of everything the person holds has nothing to compare them with.

Test these in order. The first match is the result.

| Order | Situation | Result | Why |
|---|---|---|---|
| 1 | The employee is unknown, the role is not in the table, or the table has no row for this role and item | Undetermined | There is no limit to apply. |
| 2 | A unit of this item has a missing, unreadable, or future acquired date | Undetermined | The schedule cannot be computed from that date. |
| 3 | The count is already above the maximum | Undetermined | The file disagrees with the table. A denial would hide that. |
| 4 | The count is below the maximum | Eligible | Another unit fits. This includes a first unit. A maximum of zero does not. |
| 5 | The count equals the maximum, and the oldest unit is due | Eligible | This is a replacement of that unit, not an extra one. |
| 6 | Anything else | Ineligible | The holding is already at the maximum, and nothing is due. |

## Decision

The agent approves when `check_request_eligibility` returns `eligible` and no earlier row fires: the reason is present, it names this one item, and it does not contradict what the tools returned. It denies when that tool returns `ineligible` and the reason only expresses a preference, citing the anniversary the tool returned (or the maximum when there is no unit). It escalates every other case by calling `flag_for_human_review`. It does not guess.

The agent walks these in order and stops at the first match. If two rows seem to apply, or the agent cannot tell which one applies, it escalates.

| Order | Situation | Decision | Why |
|---|---|---|---|
| 1 | Eligibility is undetermined | Escalate, naming the cause the tool returned | The table could not be applied. |
| 2 | The reason is empty or only whitespace | Escalate | The request is incomplete. It is not a request the policy refuses. |
| 3 | The reason asks for a different item than the one submitted, or for more than one item | Escalate | One request is one item. The handler does not choose. |
| 4 | The reason contradicts the item, the count, or an acquired date the tool returned | Escalate | The file and the employee disagree, and the handler does not pick a side. |
| 5 | Ineligible, and the reason claims loss, damage, or an accommodation the table does not represent | Escalate | The table only knows counts and dates. A person has to grant anything else. |
| 6 | Eligible | Approve, citing the tool result | The table already allows it. Do not say an exception was granted. That would create a precedent the table does not have. |
| 7 | Ineligible, and the reason only expresses a preference for the item | Deny. Cite the anniversary the tool returned. If there is no unit, cite the maximum. | The employee wants something the limit has not opened. With no unit, the maximum is what refused it, not a date. |
| 8 | Anything else | Escalate | This is the default. An unrecognised reason is not a denial. |

A claim that the item was lost or damaged is not, by itself, a contradiction of the file. The file can still list the unit. That claim is row 5 when the request is ineligible, and it does not block row 6 when the request is already eligible.

`flag_for_human_review(employee_id, request, basis)` records an escalation and does not approve or deny. `basis` is the row that fired and the cause. The employee's text stays the `reason`. The file is unchanged.

The draft states the decision and the values the tools returned. It does not add a product model, a price, or a ship date, because none of those are in the policy or the file.

## Demonstrations

Each fixture is built from today and from the interval in the table, so a change to the table does not leave a stale date behind. The submitted item is the one named here.

1. **Approve.** A standard employee with one monitor, oldest anniversary today or earlier. Item: monitor. Reason: the monitor is old and they want a refresh. Row 6.
2. **Deny.** A standard employee with one laptop, anniversary still ahead. Item: laptop. Reason: they want a faster laptop, and nothing else. Row 7.
3. **The same words, after the anniversary.** The laptop in demonstration 2, once its anniversary is today or earlier, is an approval. The reason did not change. Eligibility did. Row 6.
4. **Escalate.** A manager with one laptop, anniversary still ahead. Item: laptop. Reason: the laptop was stolen. Row 5.
5. **Escalate.** Any known employee. Item: a drawing tablet, which has no row. Reason: they need one. Row 1.
