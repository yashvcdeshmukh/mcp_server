"""Plan, ReAct cycle, and reflection for one equipment request."""

import json
import logging
import re
import sys
from typing import Any

import anyio
from mcp.client.session_group import ClientSessionGroup
from ollama import chat
from pydantic import BaseModel, Field, ValidationError

from equipment_mcp.agent.client import call_tool, connect, tool_list

MODEL = "qwen3:8b"
CYCLES = 8
CONTEXT = 8192
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)

ROWS = """
Stop at the first situation that is true. A missing eligibility result is not one of these.
1. The tool returned undetermined. Escalate, and the basis names that cause.
2. The reason is empty. Escalate.
3. The reason asks for a different item, or for more than one item. Escalate.
4. The reason contradicts the item, the count, or a date in the payload. Escalate.
5. The tool returned ineligible, and the reason claims loss, damage, or an accommodation. Escalate.
6. The tool returned eligible. Approve, and cite that result. Do not say an exception was granted.
7. The tool returned ineligible, and the reason is only a preference. Deny, and cite the anniversary. If there is no unit, cite the maximum.
8. Anything else. Escalate.
""".strip()

CLAIMS = ["preference", "damage", "loss", "accommodation", "different_item", "none", "other"]
ROW_RESULT = {1: "undetermined", 5: "ineligible", 6: "eligible", 7: "ineligible"}
ROW_CLAIM = {
    2: {"none"},
    3: {"different_item"},
    5: {"damage", "loss", "accommodation"},
    7: {"preference"},
}
ROW_OUTCOME = {6: "approve", 7: "deny"}

PLAN_TASK = """
Write approach as a short high-level plan for this request, in three or four plain sentences. Say who is asking and for what. Say the facts you will gather, in this order: the employee's record, then the policy limits for that role, then eligibility for the item. Say what the reason claims and how the eligibility result and that claim will lead to approve, deny, or escalate. Say that the draft will be checked against the tool results before it is final. Do not name a tool, and do not pick the outcome yet. Return employee_id as the request writes it. Return item as laptop, monitor, or headset. A MacBook is a laptop. If the request names something else, return those words. Return claim as what the reason says: damage when the item is broken, cracked, or failing; loss when it is lost or stolen; accommodation for a medical or access need; preference for wanting something newer, faster, or nicer; different_item when the reason asks for an item other than the one requested, or for more than one; none when there is no reason; other otherwise. Leave a field empty when the request does not say it. Do not choose approve, deny, or escalate. Do not invent an employee, a date, or a tool result.
""".strip()

THOUGHT_TASK = """
Using only the payload, say what you know and the one next action, in one or two sentences. Until the payload has an eligibility result, the next action gathers the next missing fact in this order: the employee's record, then the policy limits for that role, then eligibility for the item. Once it has one, name the first situation that is true by its number and say why, using the claim in the plan. A missing eligibility result is not an undetermined result. Do not quote the situations. Do not submit until an eligibility result is in the payload. If the payload has a rejected action, change only what the error names and keep everything else the same.
""".strip()

ACTION_TASK = """
Return one action. outcome is approve, deny, or escalate. The item you send is laptop, monitor, or headset. A MacBook is a laptop. If the request names something else, send the words it uses. The draft is one or two sentences a person can read. It states the outcome and says why: the eligibility result, the anniversary when there is one, and what the reason claims. It cites only values present in the payload. Do not quote the situations. Do not submit until an eligibility result is in the payload. A denial cites the anniversary in the payload, or the maximum from the limits when the payload has no unit. row is the number of the first situation that is true. cause is a few words for why, such as "cracked screen". When the tool returned undetermined, cause is the tool's cause. Gather facts in this order: the employee's record, then the policy limits for that role, then eligibility for the item. Do not compute a date. Do not mention a product model, a price, or a ship date. If the payload has no employee id, no item, or no reason, ask the user for the missing one. Do not copy these instructions into the draft. If the payload has a rejected action, change only what the error names and keep everything else the same.
""".strip()

OBSERVATION_TASK = """
Restate the payload in one or two sentences. Name the fields that are present. If it is an error, quote the error and do not say a tool returned a result. Do not choose a row. Do not decide.
""".strip()

_SNAPSHOT_KEYS = ("mode", "tool", "arguments", "row", "outcome", "draft")
_OUTCOME_WORDS = {
    "approve": {"approve", "approved"},
    "deny": {"deny", "denied"},
    "escalate": {"escalate", "escalated"},
}


class Plan(BaseModel):
    approach: str = ""
    employee_id: str = ""
    item: str = ""
    claim: str = ""


class Action(BaseModel):
    mode: str
    tool: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    question: str = ""
    outcome: str = ""
    row: int = 0
    cause: str = ""
    draft: str = ""


class Reflection(BaseModel):
    matches_tools: bool
    unconfirmed: list[str] = Field(default_factory=list)
    revised_draft: str
    decision_supported: bool


def prepare_request(sentence: str) -> str:
    text = sentence.strip()
    if not text:
        raise SystemExit("the request is empty")
    if "</user_query>" in text.lower():
        raise SystemExit("the request contains a closing user_query tag")
    return text


def validate_action(data: dict[str, Any]) -> Action:
    action = Action.model_validate(data)
    if action.mode == "call_tool":
        if not action.tool:
            raise ValueError("call_tool needs a tool name")
    elif action.mode == "ask_user":
        if not action.question.strip():
            raise ValueError("ask_user needs a question")
    elif action.mode == "submit":
        if action.outcome not in {"approve", "deny", "escalate"}:
            raise ValueError("submit needs approve, deny, or escalate")
        if action.row not in range(1, 9):
            raise ValueError("submit needs a decision row from 1 to 8")
        if not action.draft.strip():
            raise ValueError("submit needs a draft")
    else:
        raise ValueError("mode must be call_tool, ask_user, or submit")
    return action


def _check_schema(arguments: dict[str, Any], schema: dict[str, Any], where: str) -> None:
    if schema.get("type") != "object":
        return
    properties = schema.get("properties") or {}
    for key in schema.get("required") or []:
        if key not in arguments:
            raise ValueError(f"missing {where}{key}")
    for key, value in arguments.items():
        spec = properties.get(key)
        if not isinstance(spec, dict):
            continue
        expected = spec.get("type")
        if expected == "string" and not isinstance(value, str):
            raise ValueError(f"{where}{key} must be a string")
        if expected == "object":
            if not isinstance(value, dict):
                raise ValueError(f"{where}{key} must be an object")
            _check_schema(value, spec, f"{where}{key}.")


def validate_arguments(
    tool: str,
    arguments: dict[str, Any],
    sentence: str,
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check a tool call against the schema the server published. A review record keeps the original sentence."""
    schema = next((item["input_schema"] for item in tools if item["name"] == tool), None)
    if not isinstance(schema, dict):
        raise ValueError(f"unknown tool: {tool}")
    _check_schema(arguments, schema, "")
    checked = dict(arguments)
    if _records_review(schema):
        request = checked.get("request")
        if not isinstance(request, dict) or not request.get("item"):
            raise ValueError("the request needs an item")
        checked["request"] = {**request, "reason": sentence}
    return checked


def _records_review(schema: dict[str, Any]) -> bool:
    properties = schema.get("properties") or {}
    return "basis" in properties and "request" in properties


def _review_tool(tools: list[dict[str, Any]]) -> str:
    for tool in tools:
        schema = tool.get("input_schema")
        if isinstance(schema, dict) and _records_review(schema):
            return str(tool["name"])
    raise ValueError("no tool records a review")


def _is_eligibility(raw: dict[str, Any]) -> bool:
    if "error" in raw or raw.get("is_error"):
        return False
    structured = raw.get("structured") or {}
    return isinstance(structured, dict) and "result" in structured and "anniversary" in structured


def _is_review(raw: dict[str, Any]) -> bool:
    if "error" in raw or raw.get("is_error"):
        return False
    structured = raw.get("structured") or {}
    return isinstance(structured, dict) and "basis" in structured and "request" in structured


def apply_reply(plan: Plan, reply: str) -> None:
    text = reply.strip()
    if not text:
        return
    if not plan.employee_id:
        plan.employee_id = text.lower()
    elif not plan.item:
        plan.item = text.lower()


def saw_eligibility(history: list[dict[str, Any]]) -> bool:
    return any(_is_eligibility(turn.get("raw") or {}) for turn in history)


def _first_word(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    return stripped.split(None, 1)[0].lower().strip(".,:;!?\"'`")


def _leads_with(draft: str, outcome: str) -> bool:
    return _first_word(draft) in _OUTCOME_WORDS[outcome]


def _names_other(draft: str, outcome: str) -> bool:
    others = [word for name, forms in _OUTCOME_WORDS.items() if name != outcome for word in forms]
    pattern = r"\b(?:" + "|".join(sorted(others, key=len, reverse=True)) + r")\b"
    return re.search(pattern, draft.lower()) is not None


def _object(text: str) -> dict[str, Any]:
    body = text.strip()
    try:
        value = json.loads(body)
    except json.JSONDecodeError:
        start = body.find("{")
        end = body.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(body[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model reply was not an object")
    return value


def _tagged(sentence: str) -> str:
    return f"<user_query>\n{sentence}\n</user_query>"


def _snapshot(data: dict[str, Any]) -> dict[str, Any]:
    return {key: data[key] for key in _SNAPSHOT_KEYS if key in data}


def _view(sentence: str, plan: Plan, history: list[dict[str, Any]]) -> str:
    """The latest result of every tool stays in view, so a gathered fact is never lost."""
    facts: dict[str, Any] = {}
    held: dict[str, Any] | None = None
    for turn in history:
        raw = turn.get("raw") or {}
        if raw.get("tool") and "error" not in raw and not raw.get("is_error"):
            facts[raw["tool"]] = raw.get("structured")
        if "error" in raw:
            held = raw
        elif held is not None and not _review_keeps_submit(held, raw):
            held = None
    return json.dumps(
        {
            "request": _tagged(sentence),
            "plan": plan.model_dump(),
            "facts": facts,
            "error": held,
            "recent": [_without_rejected(turn) for turn in history[-2:]],
        }
    )


def _review_keeps_submit(held: dict[str, Any], raw: dict[str, Any]) -> bool:
    rejected = held.get("rejected") or {}
    return _is_review(raw) and rejected.get("mode") == "submit"


def _without_rejected(turn: dict[str, Any]) -> dict[str, Any]:
    raw = dict(turn.get("raw") or {})
    raw.pop("rejected", None)
    return {**turn, "raw": raw}


def _catalog(tools: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"- {tool['name']}: {tool['description']} arguments={json.dumps(tool['input_schema'])}"
        for tool in tools
    )


def _messages(
    task: str,
    payload: str,
    *,
    rows: list[int] | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """System holds the job. The user message holds only the request and the payload."""
    parts = ["You handle one IT equipment request.", task]
    if rows:
        parts.append("Use these situations in order. Do not quote them.\n" + _situations(rows))
    if tools is not None:
        parts.append("Tools:\n" + _catalog(tools))
    return [
        {"role": "system", "content": "\n\n".join(parts)},
        {"role": "user", "content": payload},
    ]


def _situations(rows: list[int]) -> str:
    """Only the rows the facts still allow, so the model cannot copy one that cannot apply."""
    header, *lines = ROWS.splitlines()
    return "\n".join([header, *(line for line in lines if int(line.split(".")[0]) in rows)])


def _open_rows(plan: Plan, history: list[dict[str, Any]]) -> list[int]:
    return _fitting_rows(_last_result(history), plan.claim) if saw_eligibility(history) else []


def _plan_schema() -> dict[str, Any]:
    schema = Plan.model_json_schema()
    schema["properties"]["claim"] = {"type": "string", "enum": CLAIMS}
    schema["required"] = list(schema["properties"])
    return schema


def _action_schema(tools: list[dict[str, Any]], rows: list[int]) -> dict[str, Any]:
    """Until an eligibility result exists, the model can only gather facts or ask."""
    properties: dict[str, Any] = {
        "mode": {"type": "string", "enum": ["call_tool", "ask_user"]},
        "tool": {"type": "string", "enum": ["", *(tool["name"] for tool in tools)]},
        "arguments": {"type": "object"},
        "question": {"type": "string"},
    }
    if rows:
        properties["mode"]["enum"].append("submit")
        properties["outcome"] = {"type": "string", "enum": ["approve", "deny", "escalate"]}
        properties["row"] = {"type": "integer", "enum": rows}
        properties["cause"] = {"type": "string"}
        properties["draft"] = {"type": "string"}
    return {"type": "object", "properties": properties, "required": list(properties)}


async def _complete(messages: list[dict[str, str]], schema: dict[str, Any] | None) -> str:
    def run() -> str:
        reply = chat(
            model=MODEL,
            messages=messages,
            think=False,
            format=schema,
            options={"num_ctx": CONTEXT},
        )
        return reply.message.content or ""

    return await anyio.to_thread.run_sync(run)


async def run(sentence: str) -> None:
    """Decide one request. The MCP server is already running."""
    sentence = prepare_request(sentence)
    async with connect() as group:
        tools = tool_list(group)
        plan_text = await _complete(
            _messages(PLAN_TASK, _tagged(sentence), tools=tools),
            _plan_schema(),
        )
        try:
            plan = Plan.model_validate(_object(plan_text))
        except (ValidationError, ValueError, json.JSONDecodeError):
            plan = Plan()
        print("Plan:", plan.approach)
        print("Plan fields:", json.dumps(plan.model_dump(exclude={"approach"})))

        history: list[dict[str, Any]] = []
        flagged = False
        decision: Action | None = None
        for _cycle in range(CYCLES):
            state = _view(sentence, plan, history)
            rows = _open_rows(plan, history)
            thought = await _complete(
                _messages(THOUGHT_TASK, state, rows=rows, tools=tools),
                None,
            )
            print("Thought:", thought)
            action_text = await _complete(
                _messages(
                    ACTION_TASK,
                    state + "\n\nThought:\n" + thought,
                    rows=rows,
                    tools=tools,
                ),
                _action_schema(tools, rows),
            )
            print("Action:", action_text)
            try:
                data = _object(action_text)
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                payload: dict[str, Any] = {"error": str(exc)}
            else:
                if data.get("mode") == "submit" and not saw_eligibility(history):
                    payload = {
                        "error": "submit requires an eligibility result first",
                        "rejected": _snapshot(data),
                    }
                else:
                    try:
                        action = validate_action(data)
                    except (ValidationError, ValueError) as exc:
                        payload = {"error": str(exc), "rejected": _snapshot(data)}
                    else:
                        payload = await _act(group, action, sentence, history, tools, plan)
                        if "error" in payload:
                            payload = {**payload, "rejected": _snapshot(action.model_dump())}
                        elif action.mode == "call_tool" and _is_review(payload):
                            flagged = True
                        elif action.mode == "submit":
                            decision = action
                            if action.outcome == "escalate" and not flagged:
                                review = await _flag(
                                    group,
                                    tools,
                                    plan,
                                    sentence,
                                    f"row {action.row}: {action.cause or 'escalate'}",
                                    history,
                                )
                                flagged = "error" not in review
                                print("Observation:", json.dumps(review))

            print("Result:", json.dumps({k: v for k, v in payload.items() if k != "content"}))
            observation = await _complete(
                _messages(OBSERVATION_TASK, json.dumps(payload)),
                None,
            )
            print("Observation:", observation)
            history.append({"raw": payload, "observation": observation})
            if decision is not None:
                break

        if decision is None:
            payload = await _flag(group, tools, plan, sentence, "step cap: no decision", history)
            print("Observation:", json.dumps(payload))
            if not saw_eligibility(history):
                print("This request is escalated because no eligibility result came back.")
            else:
                print("This request is escalated because no decision was reached.")
            return
        final, basis = await _settle(sentence, plan, history, decision.draft, decision.outcome)
        if final is not None:
            print(final)
            return
        if basis and not flagged:
            payload = await _flag(group, tools, plan, sentence, basis, history)
            print("Observation:", json.dumps(payload))
        print(f"This request is escalated for human review ({basis}).")


async def _act(
    group: ClientSessionGroup,
    action: Action,
    sentence: str,
    history: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    plan: Plan,
) -> dict[str, Any]:
    if action.mode == "call_tool":
        try:
            arguments = validate_arguments(action.tool, action.arguments, sentence, tools)
        except (ValidationError, ValueError) as exc:
            return {"error": str(exc)}
        return await call_tool(group, action.tool, arguments)
    if action.mode == "ask_user":
        if plan.employee_id and plan.item:
            return {"error": "the request already has an employee id and an item; call a tool"}
        print(action.question)
        reply = await anyio.to_thread.run_sync(input)
        apply_reply(plan, reply)
        return {"user": reply}
    if not saw_eligibility(history):
        return {"error": "submit requires an eligibility result first"}
    result = _last_result(history)
    fit = _fitting_rows(result, plan.claim)
    if action.row not in fit:
        return {
            "error": f"row {action.row} does not fit a {result} result and a {plan.claim or 'unread'} claim",
            "rows_that_fit": fit,
        }
    outcome = ROW_OUTCOME.get(action.row, "escalate")
    if action.outcome != outcome:
        return {"error": f"row {action.row} is {outcome}, not {action.outcome}"}
    return action.model_dump()


def _fitting_rows(result: str, claim: str) -> list[int]:
    return [
        row
        for row in range(1, 9)
        if ROW_RESULT.get(row, result) == result
        and (not claim or claim in ROW_CLAIM.get(row, {claim}))
    ]


def _last_result(history: list[dict[str, Any]]) -> str:
    result = ""
    for turn in history:
        raw = turn.get("raw") or {}
        if _is_eligibility(raw):
            result = str(raw["structured"].get("result"))
    return result


async def _flag(
    group: ClientSessionGroup,
    tools: list[dict[str, Any]],
    plan: Plan,
    sentence: str,
    basis: str,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        name = _review_tool(tools)
    except ValueError as exc:
        return {"error": str(exc)}
    employee_id, item = plan.employee_id, plan.item
    for turn in history:
        raw = turn.get("raw") or {}
        if _is_eligibility(raw):
            structured = raw["structured"]
            employee_id = structured.get("employee_id") or employee_id
            item = structured.get("item") or item
    return await call_tool(
        group,
        name,
        {
            "employee_id": employee_id or "unknown",
            "request": {"item": item or "unknown", "reason": sentence},
            "basis": basis,
        },
    )


async def _reflect(
    sentence: str,
    plan: Plan,
    history: list[dict[str, Any]],
    draft: str,
    outcome: str,
) -> Reflection:
    text = await _complete(
        _messages(
            "Check the draft against the raw payloads. Do not choose a new outcome. "
            "matches_tools is true only when every date, result, cause, and anniversary in the draft appears in the payloads. "
            "unconfirmed lists only facts the payloads do not contain: a date, a count, a result, a cause, an item, a name, a price, a product model, a ship date. Do not list wording. "
            "decision_supported is true only when the draft agrees with the payloads and the first matching row. "
            f"revised_draft is one or two full sentences written to the employee. It states {outcome}, says why in plain words, and cites only payload values such as a date or a cause. Do not quote the situations. Do not write these checks into the draft.",
            json.dumps(
                {
                    "request": _tagged(sentence),
                    "history": _view(sentence, plan, history),
                    "draft": draft,
                }
            ),
            rows=_open_rows(plan, history),
        ),
        Reflection.model_json_schema(),
    )
    try:
        return Reflection.model_validate(_object(text))
    except (ValidationError, ValueError, json.JSONDecodeError):
        return Reflection(
            matches_tools=False,
            unconfirmed=["reflection reply was not valid"],
            revised_draft=draft,
            decision_supported=False,
        )


def _quotes_rows(draft: str) -> bool:
    folded = " ".join(draft.lower().split())
    source = " ".join(ROWS.lower().split())
    return len(folded) > 20 and folded in source


async def _settle(
    sentence: str,
    plan: Plan,
    history: list[dict[str, Any]],
    draft: str,
    outcome: str,
) -> tuple[str | None, str | None]:
    reflection = await _reflect(sentence, plan, history, draft, outcome)
    print("Reflection:", reflection.model_dump_json())
    if not reflection.decision_supported or not reflection.matches_tools or reflection.unconfirmed:
        return None, "reflection: decision not supported by tool results"
    revised = reflection.revised_draft
    if _quotes_rows(revised):
        return None, "reflection: decision not supported by tool results"
    if _leads_with(revised, outcome):
        return revised, None
    if _names_other(revised, outcome):
        return None, "reflection: draft states a different outcome"
    return f"{outcome}. {revised}", None


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('usage: equipment-agent "request"')
    anyio.run(run, sys.argv[1])
