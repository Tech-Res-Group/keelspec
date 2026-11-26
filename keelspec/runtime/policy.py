"""The policy engine: decide one tool call before it runs (spec 5.3, invariant I-6).

Pure functions over the compiled bundle. Nothing here executes a tool, calls a model
or reads the network, so the same function answers ``keelspec policy explain``, the
MCP ``product_policy_explain`` tool, and the runtime's decision for a real call.
Explain and run cannot disagree, because they are the same code.

The rules, in order:

1. Collect every POL- linked from the agent whose ``match`` fits the call.
2. A policy applies only if all its ``when`` conditions hold (AND). Operators:
   ``== != > >= < <= in not_in matches exists``. No expressions, no eval.
3. Precedence: deny > require_approval > redact > allow.
4. Nothing permits it -> deny, reason ``no_policy``. Only ``allow`` and
   ``require_approval`` permit a call; ``redact`` masks a result and is never
   permission on its own.
5. A tool or operation the agent does not declare never reaches this engine: it is
   not offered to the model (``offered_operations``). Asked anyway, the engine
   denies with reason ``not_declared``.
6. Every evaluation returns a ``PolicyDecision``.
7. ``redact`` applies to results; see ``keelspec.runtime.redact``.

Fail closed: a condition that cannot be evaluated (a missing argument, a type that
does not compare, a malformed condition) makes a ``deny`` or ``require_approval``
policy apply and an ``allow`` policy not apply. Doubt never widens what an agent may
do.
"""
from __future__ import annotations

import dataclasses
import json
import re
from typing import Any

from ..agents import match_fits, operations, side_effects_of

PRECEDENCE = ("deny", "require_approval", "redact", "allow")
RESTRICTIVE = {"deny", "require_approval"}
_MISSING = object()


class Unevaluable(Exception):
    """A condition could not be decided from the arguments it was given."""


@dataclasses.dataclass(frozen=True)
class PolicyDecision:
    effect: str                          # allow | redact | require_approval | deny
    policy_ids: tuple[str, ...]          # the policies that produced the effect
    reason: str                          # human-readable, stable enough to log
    redact_classes: tuple[str, ...] = ()  # data classes to mask in the result
    approvers: tuple[str, ...] = ()      # roles that may approve, for require_approval

    @property
    def permitted(self) -> bool:
        """Whether the call may execute now, without a person."""
        return self.effect in ("allow", "redact")

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class AgentPolicies:
    """What the engine needs about one agent, resolved from the bundle once."""
    agent: dict
    tools: dict[str, dict]               # only the agent's declared tools
    policies: tuple[dict, ...]           # only the agent's linked policies

    @classmethod
    def from_bundle(cls, bundle: dict, agent_id: str) -> AgentPolicies:
        agents = {r["id"]: r for r in bundle.get("agents", [])}
        if agent_id not in agents:
            raise KeyError(f"no agent {agent_id!r} in the bundle")
        agent = agents[agent_id]
        all_tools = {r["id"]: r for r in bundle.get("tools", [])}
        all_policies = {r["id"]: r for r in bundle.get("policies", [])}
        return cls(agent,
                   {t: all_tools[t] for t in agent.get("tools") or [] if t in all_tools},
                   tuple(all_policies[p] for p in agent.get("policies") or []
                         if p in all_policies))


def offered_operations(ap: AgentPolicies) -> list[tuple[str, str]]:
    """Every (tool, operation) the agent declares: the only ones the model is shown."""
    return [(tid, op) for tid, tool in ap.tools.items() for op in operations(tool)]


# ── conditions ───────────────────────────────────────────────────────────────
def _lookup(args: Any, path: str) -> Any:
    value = args
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return _MISSING
    return value


def condition_holds(cond: dict, args: dict) -> bool:
    """Decide one ``when`` condition. Raises Unevaluable when it cannot be decided."""
    if not isinstance(cond, dict):
        raise Unevaluable("condition is not a mapping")
    op, path = cond.get("op"), cond.get("arg")
    if not isinstance(path, str):
        raise Unevaluable("condition has no arg path")
    actual = _lookup(args, path)
    if op == "exists":
        return (actual is not _MISSING) == bool(cond.get("value", True))
    if actual is _MISSING:
        raise Unevaluable(f"argument {path!r} is missing")
    expected = cond.get("value")
    try:
        if op == "==":
            return actual == expected
        if op == "!=":
            return actual != expected
        if op in (">", ">=", "<", "<="):
            if isinstance(actual, bool) or not isinstance(actual, (int, float)):
                raise Unevaluable(f"argument {path!r} is not a number")
            return {">": actual > expected, ">=": actual >= expected,
                    "<": actual < expected, "<=": actual <= expected}[op]
        if op == "in":
            return actual in expected
        if op == "not_in":
            return actual not in expected
        if op == "matches":
            return re.search(str(expected), str(actual)) is not None
    except (TypeError, re.error) as exc:
        raise Unevaluable(str(exc)) from exc
    raise Unevaluable(f"unknown op {op!r}")


def applies(policy: dict, args: dict) -> tuple[bool, str]:
    """Whether a matching policy's ``when`` holds. Fails closed (see module doc)."""
    when = policy.get("when")
    conditions = [] if when is None else when if isinstance(when, list) else [when]
    try:
        return all(condition_holds(c, args) for c in conditions), ""
    except Unevaluable as exc:
        restrictive = policy.get("effect") in RESTRICTIVE
        return restrictive, f"{policy.get('id')}: {exc}; failing closed"


# ── the decision ─────────────────────────────────────────────────────────────
def evaluate(ap: AgentPolicies, tool_id: str, operation: str,
             args: dict | None = None) -> PolicyDecision:
    """Decide one call. Deterministic: the same inputs always give the same decision."""
    args = args or {}
    tool = ap.tools.get(tool_id)
    if tool is None or operation not in operations(tool):
        return PolicyDecision("deny", (), f"not_declared: {tool_id}.{operation} is not a "
                              f"tool operation {ap.agent.get('id')} declares")

    applied: dict[str, list[dict]] = {e: [] for e in PRECEDENCE}
    notes: list[str] = []
    for pol in ap.policies:
        if not match_fits(pol.get("match"), tool, operation):
            continue
        holds, note = applies(pol, args)
        if note:
            notes.append(note)
        if holds and pol.get("effect") in applied:
            applied[pol["effect"]].append(pol)

    def ids(effect: str) -> tuple[str, ...]:
        return tuple(sorted(p["id"] for p in applied[effect]))

    redactions = tuple(sorted({c for p in applied["redact"]
                               for c in _classes(p, tool)}))
    suffix = f" ({'; '.join(notes)})" if notes else ""
    call = f"{tool_id}.{operation}"

    if applied["deny"]:
        return PolicyDecision("deny", ids("deny"), f"denied by {', '.join(ids('deny'))}{suffix}")
    if applied["require_approval"]:
        approvers = tuple(sorted({a for p in applied["require_approval"]
                                  for a in p.get("approvers") or []}))
        return PolicyDecision("require_approval", ids("require_approval"),
                              f"{call} needs approval by {', '.join(approvers) or 'a person'}"
                              f"{suffix}", redactions, approvers)
    if applied["allow"]:
        if redactions:
            return PolicyDecision("redact", ids("allow") + ids("redact"),
                                  f"allowed, with {', '.join(redactions)} masked in the result"
                                  f"{suffix}", redactions)
        return PolicyDecision("allow", ids("allow"), f"allowed by {', '.join(ids('allow'))}{suffix}")
    held = ids("redact")
    why = (f"no_policy: only {', '.join(held)} matched, and redact is not permission"
           if held else f"no_policy: no policy linked from {ap.agent.get('id')} allows {call}")
    return PolicyDecision("deny", held, why + suffix)


def _classes(policy: dict, tool: dict) -> list[str]:
    """The data classes a redact policy masks on this tool."""
    wanted = (policy.get("match") or {}).get("data_classes")
    have = tool.get("data_classes") or []
    if wanted is None:
        return list(have)
    wanted = wanted if isinstance(wanted, list) else [wanted]
    return [c for c in have if c in wanted]


def explain(bundle: dict, agent_id: str, tool_id: str, operation: str,
            args: dict | str | None = None) -> dict:
    """The decision for a hypothetical call, without executing anything.

    The same ``evaluate`` the runtime uses, plus the context a person reviewing it
    wants: the operation's side effect and every linked policy, whether it matched.
    """
    if isinstance(args, str):
        args = json.loads(args or "{}")
    ap = AgentPolicies.from_bundle(bundle, agent_id)
    decision = evaluate(ap, tool_id, operation, args or {})
    tool = ap.tools.get(tool_id)
    considered = []
    for pol in ap.policies:
        fits = bool(tool) and match_fits(pol.get("match"), tool, operation)
        considered.append({"policy": pol["id"], "effect": pol.get("effect"), "matches": fits,
                           "applies": fits and applies(pol, args or {})[0]})
    return {
        "agent": agent_id,
        "call": f"{tool_id}.{operation}",
        "side_effects": side_effects_of(tool, operation) if tool else None,
        "decision": decision.to_dict(),
        "permitted_now": decision.permitted,
        "policies": considered,
    }
