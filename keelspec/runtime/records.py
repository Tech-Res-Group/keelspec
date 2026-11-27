"""Run and step records: a closed, content-free schema (invariant I-8).

Every field is typed metadata: ids, concepts, tool names, policy decisions, token
counts, latency and outcome. There is no free-form dict anywhere, so a record cannot
quietly start carrying a prompt, a completion or a tool argument. When content
capture is on, content goes to a separate ``content.jsonl`` that a step points at
with ``content_ref``; ``run.json`` itself stays safe to ship to a SIEM.

Records live at ``.keelspec/runs/<run_id>/run.json``.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
from typing import Any

STEP_KINDS = ("model", "tool", "policy", "approval")
STEP_OUTCOMES = ("ok", "error", "denied", "refused", "timeout", "truncated")


@dataclasses.dataclass(frozen=True)
class StepRecord:
    run_id: str
    step: int
    kind: str                                   # model | tool | policy | approval
    ts_start: float
    ts_end: float
    concept: str | None = None
    served_model: str | None = None             # from x-fife-model
    router_rung: str | None = None
    router_attempts: int | None = None
    tool_id: str | None = None
    operation: str | None = None
    policy_effect: str | None = None
    policy_ids: tuple[str, ...] = ()
    policy_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    outcome: str = "ok"                         # ok | error | denied | refused | timeout | truncated
    content_ref: str | None = None              # only when capture_content is on


@dataclasses.dataclass(frozen=True)
class RunRecord:
    run_id: str
    agent_id: str
    bundle_sha256: str
    config_sha256: str
    git_commit: str
    started_at: str
    ended_at: str
    outcome: str        # completed | denied | awaiting_approval | refused:<kind> | budget_exceeded | error
    budgets_used: tuple[tuple[str, float], ...]
    capture_content: bool
    steps: tuple[StepRecord, ...]

    def to_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["budgets_used"] = dict(self.budgets_used)
        return out

    @classmethod
    def from_dict(cls, data: dict) -> RunRecord:
        problems = schema_problems(data)
        if problems:
            raise ValueError("not a valid run record: " + "; ".join(problems))
        steps = tuple(StepRecord(**{**s, "policy_ids": tuple(s.get("policy_ids") or ())})
                      for s in data["steps"])
        return cls(**{**data, "steps": steps,
                      "budgets_used": tuple(sorted((data.get("budgets_used") or {}).items()))})


_STEP_FIELDS = {f.name for f in dataclasses.fields(StepRecord)}
_RUN_FIELDS = {f.name for f in dataclasses.fields(RunRecord)}
_STEP_REQUIRED = {"run_id", "step", "kind", "ts_start", "ts_end"}


def schema_problems(data: Any) -> list[str]:
    """Everything that makes ``data`` not a run record. Closed: unknown keys fail."""
    if not isinstance(data, dict):
        return ["record is not an object"]
    problems = []
    if set(data) != _RUN_FIELDS:
        missing, extra = _RUN_FIELDS - set(data), set(data) - _RUN_FIELDS
        if missing:
            problems.append(f"missing {sorted(missing)}")
        if extra:
            problems.append(f"unknown {sorted(extra)}")
    if not isinstance(data.get("budgets_used", {}), dict) or \
            not all(isinstance(v, (int, float)) for v in (data.get("budgets_used") or {}).values()):
        problems.append("budgets_used must map names to numbers")
    for i, step in enumerate(data.get("steps") or []):
        if not isinstance(step, dict):
            problems.append(f"steps[{i}] is not an object")
            continue
        extra = set(step) - _STEP_FIELDS
        if extra:
            problems.append(f"steps[{i}] has unknown {sorted(extra)}")
        if _STEP_REQUIRED - set(step):
            problems.append(f"steps[{i}] missing {sorted(_STEP_REQUIRED - set(step))}")
        if step.get("kind") not in STEP_KINDS:
            problems.append(f"steps[{i}].kind {step.get('kind')!r}")
        if step.get("outcome", "ok") not in STEP_OUTCOMES:
            problems.append(f"steps[{i}].outcome {step.get('outcome')!r}")
        for key, value in step.items():
            if isinstance(value, dict):
                problems.append(f"steps[{i}].{key} is a mapping; records carry no free-form data")
    return problems


def run_dir(root: str | pathlib.Path, run_id: str) -> pathlib.Path:
    return pathlib.Path(root) / ".keelspec" / "runs" / run_id


def write(root: str | pathlib.Path, record: RunRecord) -> pathlib.Path:
    path = run_dir(root, record.run_id) / "run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")
    return path


def read(root: str | pathlib.Path, run_id: str) -> RunRecord:
    path = run_dir(root, run_id) / "run.json"
    return RunRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))


def list_runs(root: str | pathlib.Path) -> list[RunRecord]:
    """Every agent run record, oldest first. Unreadable ones are skipped."""
    out = []
    base = pathlib.Path(root) / ".keelspec" / "runs"
    for path in sorted(base.glob("*/run.json")):
        try:
            out.append(RunRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError):
            continue
    return sorted(out, key=lambda r: r.started_at)
