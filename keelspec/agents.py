"""Library checks for governed agents (``presets: [agents]``): PAC-070..PAC-077.

These run inside ``validate`` -- the one judge -- only when the ``agents`` preset is
enabled. They reason statically about what an agent *could* do: which operations
its tools offer, which of its policies would match each one, and whether its
scenarios exercise things it can actually call. Nothing here executes a tool or
calls a model.

The matching helpers (``operations``, ``side_effects_of``, ``match_fits``,
``when_problems``) are shared with the runtime policy engine, so the check that a
policy *would* match and the decision that it *does* cannot drift apart.

Codes raised here:

- PAC-070  a linked policy names an operation its tool does not declare
- PAC-071  an operation no linked policy permits (warning; it would always be denied)
- PAC-072  a policy's ``match`` or ``when`` is malformed
- PAC-074  a high-criticality agent can reach a money operation with no
           ``require_approval`` or ``deny`` in front of it
- PAC-075  an agent with no scenarios (warning)
- PAC-077  a scenario names a tool operation its agent cannot call
"""
from __future__ import annotations

import re
from typing import Any

from .config import Config
from .diagnostics import Report

# Effects that let a call execute. `redact` is not one: it masks a result, and a
# redact policy alone must not become permission to call every tool that touches
# that data class (spec 5.3 rule 4: every operation needs an explicit allow).
PERMITTING = {"allow", "require_approval"}
GUARDING = {"require_approval", "deny"}
MATCH_KEYS = {"tool", "operation", "side_effects", "data_classes"}
WHEN_KEYS = {"arg", "op", "value"}
OPS = {"==", "!=", ">", ">=", "<", "<=", "in", "not_in", "matches", "exists"}
ORDERED = {">", ">=", "<", "<="}
ARG_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*$")
SIDE_EFFECTS = ("none", "read", "write", "money")


def enabled(config: Config) -> bool:
    return "agents" in config.presets


# ── shared helpers ───────────────────────────────────────────────────────────
def operations(tool: dict) -> dict[str, dict]:
    """A tool's declared operations by name."""
    out: dict[str, dict] = {}
    for op in tool.get("operations") or []:
        if isinstance(op, dict) and op.get("name"):
            out[str(op["name"])] = op
        elif isinstance(op, str):
            out[op] = {"name": op}
    return out


def side_effects_of(tool: dict, operation: str) -> str:
    """An operation's side effect: its own, else the tool's, else 'none'."""
    op = operations(tool).get(operation) or {}
    return str(op.get("side_effects") or tool.get("side_effects") or "none")


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def match_fits(match: dict, tool: dict, operation: str) -> bool:
    """Whether a policy's ``match`` covers a call to ``tool.operation``.

    Every key present must fit; absent keys do not constrain. ``side_effects`` and
    ``data_classes`` accept one value or a list; ``data_classes`` fits when the tool
    handles any of them.
    """
    if not isinstance(match, dict) or not match:
        return False
    if "tool" in match and match["tool"] != tool.get("id"):
        return False
    if "operation" in match and match["operation"] != operation:
        return False
    if "side_effects" in match and \
            side_effects_of(tool, operation) not in _as_list(match["side_effects"]):
        return False
    return not ("data_classes" in match and
                not set(_as_list(match["data_classes"])) & set(_as_list(tool.get("data_classes"))))


def _conditions(when: Any) -> list:
    if when is None:
        return []
    return when if isinstance(when, list) else [when]


def when_problems(when: Any) -> list[str]:
    """Everything wrong with a ``when`` block; an empty list means it is well formed."""
    if when is not None and not isinstance(when, (dict, list)):
        return ["when must be a condition or a list of conditions"]
    problems = []
    for i, cond in enumerate(_conditions(when)):
        at = f"when[{i}]" if isinstance(when, list) else "when"
        if not isinstance(cond, dict):
            problems.append(f"{at} is not a mapping")
            continue
        extra = set(cond) - WHEN_KEYS
        if extra:
            problems.append(f"{at} has unknown key(s) {sorted(extra)}")
        arg, op = cond.get("arg"), cond.get("op")
        if not isinstance(arg, str) or not ARG_PATH.match(arg):
            problems.append(f"{at}.arg {arg!r} is not a dotted path into the tool arguments")
        if op not in OPS:
            problems.append(f"{at}.op {op!r} is not one of {sorted(OPS)}")
            continue
        value = cond.get("value")
        if op != "exists" and "value" not in cond:
            problems.append(f"{at} needs a value for op {op!r}")
        elif op in ("in", "not_in") and not isinstance(value, list):
            problems.append(f"{at}.value must be a list for op {op!r}")
        elif op in ORDERED and (isinstance(value, bool) or not isinstance(value, (int, float))):
            problems.append(f"{at}.value must be a number for op {op!r}")
        elif op == "matches":
            try:
                re.compile(str(value))
            except re.error as exc:
                problems.append(f"{at}.value is not a valid pattern: {exc}")
        elif op == "exists" and "value" in cond and not isinstance(value, bool):
            problems.append(f"{at}.value must be true or false for op 'exists'")
    return problems


def match_problems(match: Any) -> list[str]:
    if not isinstance(match, dict) or not match:
        return ["match must be a non-empty mapping"]
    problems = []
    extra = set(match) - MATCH_KEYS
    if extra:
        # An unknown key would be ignored, which widens the match. Fail closed.
        problems.append(f"match has unknown key(s) {sorted(extra)}; known: {sorted(MATCH_KEYS)}")
    bad = [s for s in _as_list(match.get("side_effects")) if s not in SIDE_EFFECTS]
    if bad:
        problems.append(f"match.side_effects {bad} not in {list(SIDE_EFFECTS)}")
    return problems


def _ref(text: Any) -> tuple[str, str] | None:
    """'TOOL-x.op' -> ('TOOL-x', 'op')."""
    if not isinstance(text, str) or "." not in text:
        return None
    tool, _, op = text.partition(".")
    return tool, op


# ── the checks ───────────────────────────────────────────────────────────────
def validate(bundle: dict, config: Config, report: Report) -> None:
    """Run PAC-070..PAC-077 over a loaded bundle. Called by ``engine.validate``."""
    tools = {r["id"]: r for r in bundle.get("tools", []) if r.get("id")}
    policies = {r["id"]: r for r in bundle.get("policies", []) if r.get("id")}
    agents = {r["id"]: r for r in bundle.get("agents", []) if r.get("id")}
    scenarios = bundle.get("scenarios", [])

    for tool in tools.values():
        for op in operations(tool).values():
            se = op.get("side_effects")
            if se is not None and se not in SIDE_EFFECTS:
                report.add("PAC-030", f"operation '{op['name']}' side_effects '{se}' "
                           f"not in {list(SIDE_EFFECTS)}", tool["_file"],
                           field="operations", value=str(se))

    for pol in policies.values():
        for problem in match_problems(pol.get("match")) + when_problems(pol.get("when")):
            field = "match" if problem.startswith("match") else "when"
            report.add("PAC-072", f"{pol['id']}: {problem}", pol["_file"], field=field)

    for agent in agents.values():
        _check_agent(agent, tools, policies, scenarios, report)

    for scn in scenarios:
        agent = agents.get(scn.get("agent"))
        if agent is not None:
            _check_scenario(scn, agent, tools, report)


def _check_agent(agent: dict, tools: dict, policies: dict, scenarios: list,
                 report: Report) -> None:
    where = agent["_file"]
    own_tools = [tools[t] for t in _as_list(agent.get("tools")) if t in tools]
    own_policies = [policies[p] for p in _as_list(agent.get("policies")) if p in policies]

    # PAC-070: a linked policy names an operation its tool does not declare.
    for pol in own_policies:
        match = pol.get("match") if isinstance(pol.get("match"), dict) else {}
        op = match.get("operation")
        if not op:
            continue
        if match.get("tool"):
            tool = tools.get(match["tool"])
            if tool is not None and op not in operations(tool):
                report.add("PAC-070", f"{pol['id']} names {match['tool']}.{op}, which "
                           f"{match['tool']} does not declare", where,
                           field="policies", value=pol["id"])
        elif not any(op in operations(t) for t in own_tools):
            report.add("PAC-070", f"{pol['id']} names operation '{op}', which none of "
                       f"this agent's tools declare", where, field="policies", value=pol["id"])

    high = agent.get("criticality") == "high"
    for tool in own_tools:
        for op in operations(tool):
            fitting = [p for p in own_policies if match_fits(p.get("match"), tool, op)]
            effects = {p.get("effect") for p in fitting}
            always_denied = any(p.get("effect") == "deny" and not _conditions(p.get("when"))
                                for p in fitting)
            # PAC-071: nothing permits it, and nothing says the denial is deliberate.
            if not effects & PERMITTING and not always_denied:
                report.add("PAC-071", f"{tool['id']}.{op} has no allow policy and would "
                           f"always be denied", where, "warning",
                           field="policies", value=f"{tool['id']}.{op}")
            # PAC-074: the money path needs a person or a deny in front of it.
            if high and side_effects_of(tool, op) == "money" and not effects & GUARDING:
                report.add("PAC-074", f"{tool['id']}.{op} moves money and no "
                           f"require_approval or deny policy covers it", where,
                           field="policies", value=f"{tool['id']}.{op}")

    # PAC-075: no scenario, either linked from the agent or pointing at it.
    linked = _as_list(agent.get("scenarios"))
    pointing = [s for s in scenarios if s.get("agent") == agent["id"]]
    if not linked and not pointing:
        report.add("PAC-075", f"{agent['id']} has no scenarios", where, "warning",
                   field="scenarios")


def _check_scenario(scn: dict, agent: dict, tools: dict, report: Report) -> None:
    """PAC-077: every operation a scenario names must be callable by its agent."""
    where = scn["_file"]
    callable_ = {(t, op) for t in _as_list(agent.get("tools")) if t in tools
                 for op in operations(tools[t])}

    named: list[tuple[str, str]] = []
    fixtures = scn.get("fixtures") if isinstance(scn.get("fixtures"), dict) else {}
    named += [("fixtures", k) for k in fixtures]
    expect = scn.get("expect") if isinstance(scn.get("expect"), dict) else {}
    for key in ("must_call", "must_not_call", "call_order"):
        named += [(f"expect.{key}", v) for v in _as_list(expect.get(key))]

    for field, text in named:
        ref = _ref(text)
        if ref is None:
            report.add("PAC-077", f"{field} entry {text!r} is not TOOL-id.operation", where,
                       field=field.split(".")[0], value=str(text))
        elif ref not in callable_:
            report.add("PAC-077", f"{field} names {text}, which {agent['id']} cannot call",
                       where, field=field.split(".")[0], value=str(text))
