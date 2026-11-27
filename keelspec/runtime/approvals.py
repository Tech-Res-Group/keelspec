"""Two-phase approval, as a file -- the same pattern as the disambiguation gate.

When a policy says ``require_approval``, the run writes
``.keelspec/approvals/<run_id>.json`` and stops in ``awaiting_approval``. A person
approves (``keelspec approvals approve <run_id> <step> --by NAME``) and the run is
resumed (``keelspec run --resume <run_id>``). The name is self-asserted, so commit
the file: the commit that fills in ``approved_by`` is the signature.

The file records which call is waiting -- tool, operation, the policies and roles --
but not the call's arguments: those stay in the run's resume state, beside the
conversation, and are deleted when the run ends.
"""
from __future__ import annotations

import datetime
import json
import pathlib


def path(root: str | pathlib.Path, run_id: str) -> pathlib.Path:
    return pathlib.Path(root) / ".keelspec" / "approvals" / f"{run_id}.json"


def request(root, run_id: str, agent_id: str, step: int, tool_id: str, operation: str,
            policy_ids, approvers) -> pathlib.Path:
    target = path(root, run_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = read(root, run_id) or {"run_id": run_id, "agent_id": agent_id, "requests": []}
    data["requests"].append({
        "step": step, "tool_id": tool_id, "operation": operation,
        "policy_ids": list(policy_ids), "approvers": list(approvers),
        "status": "pending", "approved_by": "", "approved_at": "",
    })
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    return target


def read(root, run_id: str) -> dict | None:
    target = path(root, run_id)
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def pending(root, run_id: str, step: int) -> dict | None:
    data = read(root, run_id) or {}
    return next((r for r in data.get("requests", []) if r["step"] == step), None)


def approve(root, run_id: str, step: int, by: str) -> dict:
    """Sign one pending request. Returns it; raises if there is nothing to sign."""
    if not by.strip():
        raise ValueError("an approval needs a name (--by)")
    data = read(root, run_id)
    if data is None:
        raise KeyError(f"no approval requests for run {run_id}")
    req = next((r for r in data["requests"] if r["step"] == step), None)
    if req is None:
        raise KeyError(f"run {run_id} has no approval request at step {step}")
    req["status"] = "approved"
    req["approved_by"] = by.strip()
    req["approved_at"] = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    path(root, run_id).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8",
                                  newline="\n")
    return req


def all_requests(root) -> list[dict]:
    base = pathlib.Path(root) / ".keelspec" / "approvals"
    out = []
    for p in sorted(base.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        out += [{"run_id": data["run_id"], "agent_id": data.get("agent_id"), **r}
                for r in data.get("requests", [])]
    return out
