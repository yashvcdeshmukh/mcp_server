# Equipment request requirements

This document is the policy for the IT equipment request handler. A request is approved, denied, or escalated only by the rules below.

Every pair of eligibility status and reason class has a row in the final-decision table. An eligible request whose reason is unclassified is approved under row 10. An ineligible unclassified request is escalated as `reason_unclassified`. The handler does not add a catalog item, a role, or a limit that this document does not list.

## Clock

Dates are calendar dates. At the start of a decision the handler reads today's date once, in the local timezone of the process that computes eligibility, and reuses that date for the tool result and the draft. Call it `as_of`. It is not a stored constant. A decision does not read the clock a second time.

A unit's age runs from its `acquired_on` to that `as_of`.

Offsets are built like this wherever this document subtracts whole years or months from `as_of`, including the hypothetical acquisition date for an age claim. Subtract the stated number of calendar years or months from `as_of`. Keep the same day. If that day does not exist, use the last day of the resulting month. "Acquired 4 years before `as_of`, plus 1 day" means `(as_of minus 4 calendar years) plus 1 day`. This offset rule is not the anniversary rule.

## Scope

One request asks for one unit of one item. The handler reads the employee record and this policy, then returns one decision. It does not update the equipment on file. A later request from the same employee sees the same inventory until a person changes it outside this system.

Pending and duplicate requests are out of scope. The handler does not know about an earlier request that has not yet been applied to the inventory.

## Request

The employee submits `employee_id` and `reason`.

| Field | Meaning |
|---|---|
| `employee_id` | Lookup key. Compared exactly after trimming surrounding whitespace. `e001` does not match `E001`. |
| `reason` | The employee's text. |
| `item` | Derived from `reason`, not supplied separately. |
| Decided on | `as_of`. Requests are not backdated. |

If `reason` is empty or only whitespace, stop. Escalate `reason_missing`. Otherwise derive `item` from whole words in `reason`, case-insensitive. The only catalog words are `laptop`, `monitor`, and `headset`.

- Two or more different catalog words: stop. Escalate `multiple_items`. Do this even when `employee_id` is unknown.
- Exactly one catalog word: that word is `item`. Any other product name in the text, such as `MacBook` or `screen`, is ignored. It is not mapped onto a catalog item, and it does not block the catalog word that is present.
- Zero catalog words: stop. Escalate `item_not_in_catalog`. Plurals such as `monitors` are not catalog words. Do not singularize them, and do not guess an item.

`check_request_eligibility` is called only after exactly one catalog word has been selected. Called on its own with a non-catalog name, it returns `item_not_in_catalog`.

A stated age can change the decision to `record_conflict`, under Reason classes. It does not change `acquired_on` or the due date.

## Employee record

`get_employee_info(employee_id)` returns:

| Field | Meaning |
|---|---|
| `employee_id` | As stored. |
| `name` | Display name. Not used in the decision. |
| `role` | Compared after trim and lowercase. `standard` or `manager`. |
| `start_date` | Hire date. Tenure may be shown. Tenure is not an eligibility input. A missing or malformed `start_date` does not change the decision. |
| `equipment` | Zero or more units. Each unit has `item` and `acquired_on`. |

An unknown id returns `employee_not_found` and no guessed name, role, or equipment.

`standard` means an individual contributor. There is no contractor, executive, or intern role. After trim and lowercase, any other role is `unknown_role`.

Count only units whose `item`, after trim and lowercase, equals the requested catalog word. A unit stored as `MacBook` does not count as a laptop.

`acquired_on` must be a real calendar date written `YYYY-MM-DD`. Any other value, including `2026-13-45`, is `missing_acquired_on`.

## Catalog and limits

`get_policy_limits(role)` looks up the role after trim and lowercase. It returns that role's row, or `unknown_role`.

| Role | Item | Max on file | Replace a unit after |
|---|---|---|---|
| `standard` | laptop | 1 | 4 years |
| `standard` | monitor | 1 | 3 years |
| `standard` | headset | 1 | 2 years |
| `manager` | laptop | 1 | 2 years |
| `manager` | monitor | 2 | 3 years |
| `manager` | headset | 1 | 2 years |

Max on file is the most units of that item the record may hold after the request. A request moves at most one unit. Someone with none receives one unit, not their whole allowance at once.

The interval applies to each unit on its own `acquired_on`. It does not mean a batch of new units every cycle, regardless of what the person already holds.

## Eligibility

`check_request_eligibility(employee_id, item)` does not read `reason`. It returns `eligible`, `ineligible`, or `undetermined`, plus one code.

These are undetermined even when the count would otherwise allow the item:

- `employee_not_found`
- `unknown_role`
- `item_not_in_catalog`
- `missing_acquired_on` on any counted unit of the requested item
- `future_acquired_on` when any counted unit has `acquired_on` after `as_of`
- `count_exceeds_max` when the record already holds more than the max

When more than one of these applies, return the first match in this order: `employee_not_found`, `unknown_role`, `item_not_in_catalog`, `count_exceeds_max`, `missing_acquired_on`, `future_acquired_on`.

For a clean record:

| Condition | Status | Code |
|---|---|---|
| Count is 0 | eligible | `initial_issue` |
| Count is greater than 0 and less than max | eligible | `under_cap` |
| Count equals max, and the oldest unit is due | eligible | `refresh_due` |
| Count equals max, and the oldest unit is not due | ineligible | `refresh_not_due` |

The oldest unit is one with the earliest `acquired_on`. If several units share that date, they are the same age. The draft cites that date. Units have no separate id.

A unit is due on its anniversary. Add the interval in calendar years to `acquired_on`. If `acquired_on` is February 29 and the anniversary year is not a leap year, the due date is March 1 of that year. If that anniversary year is a leap year, the due date stays February 29. The unit is due when `as_of` is on or after that date.

A laptop acquired on 2024-02-29 has a 4-year anniversary of 2028-02-29, because 2028 is a leap year. Its 2-year anniversary is 2026-03-01, because 2026 is not a leap year.

`under_cap` does not look at age. A manager with one monitor acquired yesterday is eligible for a second monitor.

`initial_issue` does not look at tenure. A hire with an empty equipment list is eligible for a first laptop, monitor, or headset.

A unit acquired on `as_of` has age 0. It is on file, so the request is not an initial issue.

## Reason classes

An empty or whitespace `reason` is `reason_missing`, decided before item derivation. The classes below apply only after exactly one item has been selected and eligibility has returned. Matching is case-insensitive, on whole words. `old` does not match `told`. Before any matching, replace the typographic apostrophe `’` with `'` throughout `reason`, so `don’t` is the word `don't` and `laptop’s` is the word `laptop`. Apostrophe means `'` after that replacement, and this replacement also applies to item derivation. A word is a maximal run of letters, digits, and apostrophes, so `don't` and `won't` are single words, and every other character, including `-`, `/`, and `.`, separates words. A trailing `'s` is dropped before comparison, so `laptop's` is the word `laptop`. Two words are adjacent when no other word lies between them, whatever separators lie between them. A phrase matches only as those adjacent words. Sentences split on `.`, `!`, and `?`. A comma does not start a new sentence.

Apply the classes in the order below. The first match is the class.

**Exception.** Class: `exception`. A match is one of the templates below, including the `it was` and `it is` shapes in the following paragraph. No other wording is an exception. `<item>` is the catalog word selected for this request.

- `<item> was stolen`, `<item> is stolen`, `stolen <item>`, `my <item> was stolen`, `my <item> is stolen`
- the same five shapes for `lost`, `broken`, `damaged`, `cracked`, `defective`, `flickering`, and `dead`
- `<item> is not working`, `<item> not working`, `my <item> is not working`, `my <item> not working`
- `<item> won't turn on`, `<item> will not turn on`, `my <item> won't turn on`, `my <item> will not turn on`
- `<item> is worn out`, `<item> was worn out`, `worn out <item>`, `my <item> is worn out`
- `medical accommodation`, `accessibility accommodation`, `disability accommodation`

If the same sentence as `<item>` contains `it was stolen`, `it is stolen`, or the same `it was` / `it is` shape for `lost`, `broken`, `damaged`, `cracked`, `defective`, `flickering`, or `dead`, that is also an exception. No other pronoun counts. `not working`, `worn`, `lost`, `medical`, and `accessibility` do not match outside these templates. "I'm not working next week" is not an exception. "Worn this headset" is not an exception. "The accessibility team" is not an exception.

**Conflict.** Class: `record_conflict`. Used only when the class is not exception.

A zero claim matches only these phrases, with `<item>` and no extra words inside the phrase: `I don't have a <item>`, `I do not have a <item>`, `I have no <item>`, `I never received a <item>`. It is a conflict only when the count on file is at least 1. `I don't have a second monitor` does not match. When the count is 0, a zero claim is not a conflict.

An age claim matches only a run of digits bounded on the left by whitespace or the start of the text, then `year` or `years`, then `old`, such as `4 years old`. A number written with a decimal point, such as `2.5 years old`, is not an age claim. `last month`, `since 2022`, and `ancient` are not ages. An integer greater than 200 is not an age claim. When more than one age claim remains, use the largest integer.

An age claim is considered only when the count equals the max, because only then does the refresh clock decide eligibility. Compare it against the oldest counted unit only: replace that unit's `acquired_on` with a hypothetical acquisition N calendar years before `as_of`, using the offset rule, leave every other unit unchanged, apply the anniversary rule, and recompute the status. If that status differs from the file's status, the age claim is a conflict. The same status is not a conflict. When the count is below the max, an age claim is not a conflict.

**Ordinary.** Used when none of the classes above apply, and the text contains any whole word among: faster, slow, slower, old, outdated, refresh, replacement, replace, upgrade, newer, second, additional, another, extra.

**Unclassified.** Any other non-empty reason.

## Final decision

Walk this table in order. The first matching row is the decision. Rows 4 through 10 use the single class from Reason classes. Exception is assigned before conflict, so a reason that matches both is not row 4.

| Order | Situation | Decision |
|---|---|---|
| 1 | `reason` is empty or only whitespace | Escalate `reason_missing`. Stop before item derivation and the employee lookup. |
| 2 | The reason names two or more different catalog items, or names none | Escalate `multiple_items`, or `item_not_in_catalog` when it names none. Stop before the employee lookup. |
| 3 | Eligibility is undetermined | Escalate with the single tool code chosen by the Eligibility precedence list. |
| 4 | Reason is a conflict | Escalate `record_conflict` |
| 5 | Ineligible and the reason is an exception | Escalate `exception_claimed` |
| 6 | Eligible and the reason is an exception | Approve. The draft cites `initial_issue`, `under_cap`, or `refresh_due`. It does not say the exception was granted. |
| 7 | Ineligible and the reason is ordinary | Deny. The draft cites `refresh_not_due` and the due date. |
| 8 | Eligible and the reason is ordinary | Approve. The draft cites the policy code. |
| 9 | Ineligible and the reason is unclassified | Escalate `reason_unclassified` |
| 10 | Eligible and the reason is unclassified | Approve. The draft cites the policy code. |

A deny is only row 7. `I want a faster laptop` contains the ordinary word `faster` and does not match an exception template. After the anniversary the decision is an approval. Before the anniversary it is a denial. The anniversary carries that decision.

An exception is `exception_claimed` only when eligibility returned ineligible. When eligibility returned eligible under `initial_issue`, `under_cap`, or `refresh_due`, the request is approved under row 6, whatever the age of any unit on file.

## Escalation

`flag_for_human_review(employee_id, request, reason)` records the escalation and does not approve or deny. `request` is the original text. `reason` is the code from the table above plus one sentence naming the rule that fired. The equipment record is unchanged.

## Draft response

The draft states the decision, the code, and the facts the tools returned: role, item, count on file, max, and, when a date was used, `acquired_on` and the due date.

The draft does not add a product model, a price, a ship date, or a budget. It does not say an exception was granted. On a refresh it names the earliest `acquired_on` and states that the new unit replaces a unit acquired on that date.

## Worked examples

Offsets use the rule in Clock. The four leap-day rows are checks of the anniversary function with the `as_of` named in the row. They are not requests the running handler decides. The running handler's `as_of` is today.

| Case | Record | Reason | Result |
|---|---|---|---|
| Refresh due | Standard, one laptop acquired 4 years before `as_of` | "I want a faster laptop" | Approve `refresh_due`. The anniversary is on or before `as_of`. |
| One day early | Standard, one laptop acquired `(as_of minus 4 calendar years) plus 1 day` | "I want a faster laptop" | Deny `refresh_not_due`. Due the next day. |
| Due, and also stolen | Standard, one laptop acquired 4 years before `as_of` | "My laptop was stolen" | Approve `refresh_due`. The draft does not grant a theft exception. |
| Stolen inside the window | Manager, one laptop acquired 11 months before `as_of` | "My laptop was stolen" | Escalate `exception_claimed`. The 2-year anniversary is still after `as_of`. |
| Not an exception | Standard, one laptop acquired 16 months before `as_of` | "I'm not working next week, so I want a faster laptop" | Deny `refresh_not_due`. `not working` is outside the exception templates. `faster` is ordinary. |
| Second monitor under the cap | Manager, one monitor acquired 1 month before `as_of` | "I need a second monitor" | Approve `under_cap` |
| Cracked, but under the cap | Manager, one monitor acquired 1 month before `as_of` | "My monitor is cracked, I need a second monitor" | Approve `under_cap`. Eligible, so row 6 approves. |
| Second monitor over the cap | Standard, one monitor acquired 1 month before `as_of` | "I need a second monitor" | Deny `refresh_not_due`. Due 3 years after `acquired_on`. |
| First laptop | Standard, no laptop on file | "I want a laptop" | Approve `initial_issue`. The reason is unclassified, and row 10 approves it. |
| Vague, inside the window | Standard, one laptop acquired 16 months before `as_of` | "Please, it's important that I get a new laptop" | Escalate `reason_unclassified`. `new` is not the ordinary word `newer`. |
| No reason | Any employee id | blank | Escalate `reason_missing`, before item derivation |
| Unknown item | Any employee id | "I need a drawing tablet" | Escalate `item_not_in_catalog`. The text has no catalog word. |
| Plural | Any employee id | "I need two monitors" | Escalate `item_not_in_catalog`. `monitors` is not a catalog word. |
| Unknown employee | Id not on file | "I want a faster laptop" | Escalate `employee_not_found` |
| Age disagrees with the file | Standard, one laptop acquired 1 year before `as_of` | "My laptop is 4 years old and slow" | Escalate `record_conflict`. Count equals max. 4 years would be due; the file is not. |
| Age agrees with the file | Standard, one laptop acquired 5 years before `as_of` | "My laptop is 4 years old and slow" | Approve `refresh_due`. Both are past 4 years. |
| Age ignored under the cap | Manager, one monitor acquired 1 month before `as_of` | "My monitor is 10 years old and I need a second" | Approve `under_cap`. Count is below max, so the age claim is not a conflict. |
| Claims they have none | Standard, one monitor acquired 2 years before `as_of` | "I don't have a monitor" | Escalate `record_conflict` |
| Stolen, so they say they have none | Standard, one laptop acquired 16 months before `as_of` | "I don't have a laptop, it was stolen" | Escalate `exception_claimed`. Exception is classified before conflict. |
| Two items | Any employee id | "I need a laptop and a monitor" | Escalate `multiple_items` |
| Replacement, not a third | Manager, one monitor acquired 4 years before `as_of` and one acquired 9 months before `as_of` | "My monitor is old and I want a replacement" | Approve `refresh_due` for the older date. Count stays 2. |
| Neither monitor is due | Manager, monitors acquired 18 months and 9 months before `as_of` | "My monitor is old and I want a replacement" | Deny `refresh_not_due`. The older anniversary is still after `as_of`. |
| Leap day, not yet due | Standard, one laptop acquired 2024-02-29, and `as_of` is 2028-02-28 | "I want a faster laptop" | Deny `refresh_not_due`. The 4-year anniversary is 2028-02-29. |
| Leap day, anniversary | Same laptop, and `as_of` is 2028-02-29 | "I want a faster laptop" | Approve `refresh_due` |
| Non-leap anniversary | Manager, one laptop acquired 2024-02-29, and `as_of` is 2026-02-28 | "I want a faster laptop" | Deny `refresh_not_due`. The 2-year anniversary is 2026-03-01. |
| Non-leap, due | Same manager laptop, and `as_of` is 2026-03-01 | "I want a faster laptop" | Approve `refresh_due` |
| Already over the max | Standard, two laptops on file | "I want a faster laptop" | Escalate `count_exceeds_max` |
| Missing date | Standard, one headset with no `acquired_on` | "I want a replacement headset" | Escalate `missing_acquired_on` |

## Demo requests

These four are the end-to-end demonstrations. Build their equipment dates with the offset rule, including when `as_of` is February 29, so the approve demo stays due.

1. **Approve.** Standard employee, one monitor acquired 3 years before `as_of`, reason "My monitor is old and due for a refresh." That unit's anniversary is on or before `as_of`, so the result is `refresh_due`.
2. **Deny.** Standard employee, one laptop acquired 16 months before `as_of`, reason "I want a faster laptop."
3. **Escalate.** Manager, one laptop acquired 11 months before `as_of`, reason "My laptop was stolen."
4. **Escalate.** Any known employee, reason "I need a drawing tablet." The text has no catalog word, so the code is `item_not_in_catalog`.
