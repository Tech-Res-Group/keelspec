"""What the line has been doing, read back from the runs it kept.

Every `keelspec orchestrate` saves its report under ``.keelspec/runs/``. This adds
them up: how often the line proposes, how often it is refuted and by which lens,
what triage said the failures were, which risk tiers the work fell into, and how
long runs take.

These are measures of the line, not of the business. They say whether the factory
is healthy; whether the work it ships moves an outcome is measured in production,
against the ``outcome`` each feature traces to. Reporting one as if it were the
other is the mistake this module's name is careful not to make.
"""
from __future__ import annotations

import json
import pathlib
import statistics
from collections import Counter
from datetime import datetime


def runs_dir(root: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(root) / ".keelspec" / "runs"


def load_runs(root: str | pathlib.Path) -> list[dict]:
    """Every readable run, oldest first. A malformed file is skipped, not fatal."""
    out = []
    for path in sorted(runs_dir(root).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("feature"):
            out.append(data)
    return out


def _seconds(run: dict) -> float | None:
    try:
        start = datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(run["finished_at"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, ValueError):
        return None
    return (end - start).total_seconds()


def summarise(runs: list[dict]) -> dict:
    status = Counter(r.get("status", "unknown") for r in runs)
    refuted_by: Counter[str] = Counter()
    causes: Counter[str] = Counter()
    for run in runs:
        lenses = {lens for t in run.get("triage") or [] for lens in t.get("lenses") or []}
        lenses |= {v.get("lens") for v in run.get("verdicts") or []
                   if v.get("refuted") and v.get("severity") in {"blocker", "major"}}
        refuted_by.update(lens for lens in lenses if lens)
        causes.update(t.get("cause") for t in run.get("triage") or [] if t.get("cause"))

    built = [r for r in runs if r.get("status") in {"proposed", "refuted", "needs-human"}]
    repaired = [r for r in built if r.get("repair_rounds")]
    durations = [d for d in map(_seconds, runs) if d is not None]
    latest: dict[str, str] = {}
    for run in runs:
        latest[run["feature"]] = run.get("status", "unknown")

    return {
        "schema": "keelspec-metrics/1",
        "runs": len(runs),
        "features": len(latest),
        "status": dict(sorted(status.items())),
        "first_pass_rate": (
            round(sum(1 for r in built if r.get("status") == "proposed"
                      and not r.get("repair_rounds")) / len(built), 3) if built else None),
        "repair_rate": round(len(repaired) / len(built), 3) if built else None,
        "mean_repair_rounds": (
            round(statistics.mean(r.get("repair_rounds") or 0 for r in built), 2)
            if built else None),
        "refuted_by_lens": dict(sorted(refuted_by.items())),
        "triage_causes": dict(sorted(causes.items())),
        "risk_tiers": dict(sorted(Counter(
            (r.get("risk") or {}).get("tier") or "(none)" for r in runs).items())),
        "median_seconds": round(statistics.median(durations), 1) if durations else None,
        "latest_status": dict(sorted(latest.items())),
    }


def render_text(summary: dict) -> str:
    def pct(x):
        return "n/a" if x is None else f"{x:.0%}"

    def counts(d):
        return ", ".join(f"{k} {v}" for k, v in d.items()) or "none"

    lines = [
        f"runs: {summary['runs']} over {summary['features']} feature(s)",
        f"status: {counts(summary['status'])}",
        f"first-pass proposals: {pct(summary['first_pass_rate'])}   "
        f"needed repair: {pct(summary['repair_rate'])}   "
        f"mean repair rounds: {summary['mean_repair_rounds'] if summary['mean_repair_rounds'] is not None else 'n/a'}",
        f"refuted by lens: {counts(summary['refuted_by_lens'])}",
        f"triage causes: {counts(summary['triage_causes'])}",
        f"risk tiers: {counts(summary['risk_tiers'])}",
        f"median run: {summary['median_seconds'] if summary['median_seconds'] is not None else 'n/a'}s",
        "",
        "These measure the line. Business outcomes are measured in production, "
        "against each feature's outcome.",
    ]
    return "\n".join(lines) + "\n"
