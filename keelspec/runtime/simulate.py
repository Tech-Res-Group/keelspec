"""``keelspec simulate``: replay scenarios offline and check them (spec 5.4, M9).

Each scenario runs through the real agent loop: the real policy engine, budgets,
redaction and run records. Only two things are stood in for:

- tools answer from the scenario's ``fixtures`` (``FixtureExecutor``);
- the model is ``ScriptedModel``, a deterministic stand-in written to be
  **naive on purpose**. It investigates by calling every read-only operation it can
  fill arguments for, and it *obeys any instruction it finds in tool data*: if a
  result mentions one of its operations by name, it calls that operation next.

That is the worst case for a model, chosen so a passing scenario proves the
*policy* holds, not that a model happened to behave. With the injection scenario,
the scripted model really does try ``release_funds``; ``POL-no-funds-movement`` is
what stops it.

The ``expect`` keys are deterministic checks on the run record and the final
answer. "Called" means the tool actually ran (a ``tool`` step), not that the model
asked for it: a denied request is a policy decision, counted under
``policy_decisions``. An optional ``judge`` block is reported, never gating (I-2).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import re
import tempfile
import xml.etree.ElementTree as ET
from typing import Any

from ..agents import side_effects_of
from .agent import run_agent
from .fixtures import FixtureExecutor
from .policy import AgentPolicies
from .router_client import RouterReply, RuntimeSettings, parse_tool_name

SCRIPTED_MODEL = "keelspec-scripted/1"
READ_ONLY = {"none", "read"}
# Where the scripted model looks for an argument it has not seen in a tool result.
INPUT_PATTERNS = {
    "case_id": r"\b[Cc]ase\s+#?([A-Za-z0-9-]+)",
    "end_to_end_id": r"\b(E2E-[A-Za-z0-9-]+)\b",
    "code": r"\b([A-Z]{2}\d{2})\b",
}
ANSWER_KEYS = ("plain", "meaning")
COUNT = re.compile(r"^\s*(==|!=|>=|<=|>|<)?\s*(\d+)\s*$")


# ── the scripted model ───────────────────────────────────────────────────────
class ScriptedModel:
    """A deterministic, deliberately naive model with the router client's ``chat``."""

    def __init__(self, bundle: dict, agent_id: str):
        self.ap = AgentPolicies.from_bundle(bundle, agent_id)
        self.calls = 0

    def _side_effects(self, name: str) -> str:
        tool_id, op = parse_tool_name(name)
        return side_effects_of(self.ap.tools[tool_id], op)

    @staticmethod
    def _requested(messages: list[dict]) -> list[str]:
        return [c["function"]["name"] for m in messages if m.get("role") == "assistant"
                for c in m.get("tool_calls") or []]

    @staticmethod
    def _results(messages: list[dict]) -> list[Any]:
        out = []
        for m in messages:
            if m.get("role") != "tool":
                continue
            try:
                out.append(json.loads(m.get("content") or "null"))
            except ValueError:
                out.append(m.get("content"))
        return out

    @staticmethod
    def _find(data: Any, key: str) -> Any:
        if isinstance(data, dict):
            if key in data and isinstance(data[key], (str, int, float)):
                return data[key]
            for v in data.values():
                found = ScriptedModel._find(v, key)
                if found is not None:
                    return found
        elif isinstance(data, list):
            for v in data:
                found = ScriptedModel._find(v, key)
                if found is not None:
                    return found
        return None

    def _args(self, schema: dict, text: str, results: list[Any],
              partial: bool = False) -> dict | None:
        """Fill arguments from earlier results, then from the input; None if a
        required one cannot be filled, unless ``partial``."""
        props = (schema or {}).get("properties") or {}
        args: dict = {}
        for name in props:
            value = next((v for r in reversed(results)
                          if (v := self._find(r, name)) is not None), None)
            if value is None and name in INPUT_PATTERNS:
                m = re.search(INPUT_PATTERNS[name], text)
                value = m.group(1) if m else None
            if value is not None:
                args[name] = value
        if not partial and any(r not in args for r in (schema or {}).get("required") or []):
            return None
        return args

    def chat(self, messages: list[dict], tools: list[dict], **_: Any) -> RouterReply:
        self.calls += 1
        text = next((m["content"] for m in messages if m.get("role") == "user"), "")
        requested = set(self._requested(messages))
        results = self._results(messages)
        data_text = json.dumps(results)
        offered = [t["function"] for t in tools]

        # 1. Naive: obey any operation named in tool data (the injection path).
        for fn in offered:
            _, op = parse_tool_name(fn["name"])
            if fn["name"] not in requested and re.search(rf"\b{re.escape(op)}\b", data_text):
                args = self._args(fn.get("parameters") or {}, text, results, partial=True)
                return self._call(fn["name"], args)
        # 2. Investigate: the next read-only operation it can fill.
        for fn in offered:
            if fn["name"] in requested or self._side_effects(fn["name"]) not in READ_ONLY:
                continue
            args = self._args(fn.get("parameters") or {}, text, results)
            if args is not None:
                return self._call(fn["name"], args)
        # 3. Answer from what it saw.
        return self._reply({"role": "assistant", "content": self._answer(text, results)})

    def _call(self, name: str, args: dict) -> RouterReply:
        return self._reply({"role": "assistant", "content": None, "tool_calls": [
            {"id": f"call_{self.calls}", "type": "function",
             "function": {"name": name, "arguments": json.dumps(args)}}]})

    def _reply(self, message: dict) -> RouterReply:
        return RouterReply(message=message, served_model=SCRIPTED_MODEL, rung=None,
                           attempts=1, concept=self.ap.agent.get("concept"),
                           input_tokens=0, output_tokens=0)

    def _answer(self, text: str, results: list[Any]) -> str:
        lines = [f"Findings for: {text}"]
        for r in results:
            data = r.get("data") if isinstance(r, dict) else None
            if isinstance(data, dict) and data.get("code"):
                said = next((data[k] for k in ANSWER_KEYS if data.get(k)), "")
                name = f" ({data['name']})" if data.get("name") else ""
                lines.append(f"- {data['code']}{name}: {said}")
            elif isinstance(r, dict) and r.get("error") == "denied by policy":
                lines.append(f"- An action was refused by policy ({r.get('reason')}).")
        return "\n".join(lines)


# ── expectations ─────────────────────────────────────────────────────────────
def _count_ok(rule: Any, n: int) -> bool:
    if isinstance(rule, bool):
        return False
    if isinstance(rule, int):
        return n == rule
    m = COUNT.match(str(rule))
    if not m:
        return False
    op, value = m.group(1) or "==", int(m.group(2))
    return {"==": n == value, "!=": n != value, ">=": n >= value, "<=": n <= value,
            ">": n > value, "<": n < value}[op]


def _list(value: Any) -> list:
    return value if isinstance(value, list) else [value] if value is not None else []


def check(expect: dict, record: Any, final: str) -> list[str]:
    """Every expectation the run does not meet, as a sentence; empty means pass."""
    expect = expect if isinstance(expect, dict) else {}
    executed = [f"{s.tool_id}.{s.operation}" for s in record.steps if s.kind == "tool"]
    failures = []
    for call in _list(expect.get("must_call")):
        if call not in executed:
            failures.append(f"must_call: {call} did not run")
    for call in _list(expect.get("must_not_call")):
        if call in executed:
            failures.append(f"must_not_call: {call} ran")
    order = _list(expect.get("call_order"))
    if order:
        positions = [executed.index(c) if c in executed else -1 for c in order]
        if -1 in positions or positions != sorted(positions):
            failures.append(f"call_order: expected {' -> '.join(order)}, ran "
                            f"{' -> '.join(executed) or 'nothing'}")
    decisions = expect.get("policy_decisions")
    if isinstance(decisions, dict):
        for effect, rule in decisions.items():
            n = sum(1 for s in record.steps if s.kind == "policy" and s.policy_effect == effect)
            if not _count_ok(rule, n):
                failures.append(f"policy_decisions: {effect} {rule!s} expected, saw {n}")
    want = expect.get("outcome")
    if want and record.outcome != want and not record.outcome.startswith(f"{want}:"):
        failures.append(f"outcome: expected {want}, got {record.outcome}")
    for text in _list(expect.get("final_answer_contains")):
        if str(text) not in final:
            failures.append(f"final_answer_contains: {text!r} not in the answer")
    for text in _list(expect.get("final_answer_not_contains")):
        if str(text) in final:
            failures.append(f"final_answer_not_contains: {text!r} is in the answer")
    used = dict(record.budgets_used)
    if expect.get("max_steps") is not None and used.get("steps", 0) > expect["max_steps"]:
        failures.append(f"max_steps: {used.get('steps')} > {expect['max_steps']}")
    if expect.get("max_cost_usd") is not None and used.get("cost_usd", 0) > expect["max_cost_usd"]:
        failures.append(f"max_cost_usd: {used.get('cost_usd')} > {expect['max_cost_usd']}")
    return failures


# ── running scenarios ────────────────────────────────────────────────────────
@dataclasses.dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    agent_id: str
    file: str
    passed: bool
    failures: tuple[str, ...]
    outcome: str
    steps: int
    notes: tuple[str, ...] = ()


def select(bundle: dict, target: str | None = None) -> list[dict]:
    """The scenarios to run: all of them, one agent's, or one."""
    scenarios = bundle.get("scenarios", [])
    if not target:
        return list(scenarios)
    if target.startswith("SCN-") or any(s["id"] == target for s in scenarios):
        chosen = [s for s in scenarios if s["id"] == target]
    else:
        agent = next((a for a in bundle.get("agents", []) if a["id"] == target), None)
        if agent is None:
            raise KeyError(f"no agent or scenario {target!r} in the bundle")
        linked = set(_list(agent.get("scenarios")))
        chosen = [s for s in scenarios if s["id"] in linked or s.get("agent") == target]
    if not chosen:
        raise KeyError(f"no scenario {target!r} in the bundle")
    return chosen


def run_scenario(bundle: dict, provenance: dict, scn: dict) -> ScenarioResult:
    notes = []
    if scn.get("judge"):
        notes.append("judge rubric present: not run here; an LLM grade never gates (I-2)")
    agent_id = scn.get("agent") or ""
    with tempfile.TemporaryDirectory(prefix="keelspec-sim-") as tmp:
        try:
            result = run_agent(bundle, provenance, agent_id, str(scn.get("input") or ""),
                               root=tmp, router=ScriptedModel(bundle, agent_id),
                               executor=FixtureExecutor(scn.get("fixtures") or {}),
                               settings=RuntimeSettings(), prices={})
        except KeyError as exc:
            return ScenarioResult(scn["id"], agent_id, scn.get("_file", ""), False,
                                  (f"cannot run: {str(exc).strip(chr(39))}",), "error", 0,
                                  tuple(notes))
    failures = check(scn.get("expect") or {}, result.record, result.final_answer)
    return ScenarioResult(scn["id"], agent_id, scn.get("_file", ""), not failures,
                          tuple(failures), result.record.outcome, len(result.record.steps),
                          tuple(notes))


def simulate(bundle: dict, provenance: dict, target: str | None = None) -> list[ScenarioResult]:
    return [run_scenario(bundle, provenance, s) for s in select(bundle, target)]


# ── reports ──────────────────────────────────────────────────────────────────
def junit(results: list[ScenarioResult]) -> str:
    """JUnit XML: one test suite per agent, one test case per scenario."""
    suites = ET.Element("testsuites", name="keelspec simulate")
    by_agent: dict[str, list[ScenarioResult]] = {}
    for r in results:
        by_agent.setdefault(r.agent_id, []).append(r)
    for agent_id, rs in by_agent.items():
        suite = ET.SubElement(suites, "testsuite", name=agent_id or "(no agent)",
                              tests=str(len(rs)), failures=str(sum(not r.passed for r in rs)))
        for r in rs:
            case = ET.SubElement(suite, "testcase", classname=agent_id or "scenarios",
                                 name=r.scenario_id, file=r.file)
            if not r.passed:
                fail = ET.SubElement(case, "failure", message=r.failures[0] if r.failures else "")
                fail.text = "\n".join(r.failures)
            if r.notes:
                ET.SubElement(case, "system-out").text = "\n".join(r.notes)
    ET.indent(suites)
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(suites, encoding="unicode") + "\n"


def evidence_section(results: list[ScenarioResult], root: str | pathlib.Path,
                     provenance: dict) -> dict:
    """The ``simulation`` block of an evidence record: what ran, on which file
    contents, against which bundle, and the result."""
    root = pathlib.Path(root)

    def digest(rel: str) -> str | None:
        try:
            return hashlib.sha256((root / rel).read_bytes()).hexdigest()
        except OSError:
            return None
    return {
        "model": SCRIPTED_MODEL,
        "bundle_sha256": provenance.get("bundle_sha256", ""),
        "scenarios": [{"id": r.scenario_id, "agent": r.agent_id, "file": r.file,
                       "sha256": digest(r.file), "result": "pass" if r.passed else "fail",
                       "outcome": r.outcome, "failures": list(r.failures)}
                      for r in results],
        "result": "pass" if all(r.passed for r in results) else "fail",
    }

