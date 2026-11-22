"""What the line has been doing, read back from the runs it kept.

Every `keelspec orchestrate` saves its report under ``.keelspec/runs/``. This adds
them up: how often the line proposes, how often it is refuted and by which lens,
what triage said the failures were, which risk tiers the work fell into, and how
long runs take.

Version 2 adds four factory measures, each read from files the line already keeps:

- **rejection rate per lens**: of the runs where a critic cast a verdict, how many it
  refuted at least once. An abstention is not a pass, so it is counted separately.
- **review load**: how often the line needed a person, how many questions it asked,
  and how many required approvals were given or are still missing.
- **cost**: tokens per model call are on each run; the price per model comes from
  ``prices`` in product.config.yaml, never from this file. A vendor that reports its
  own cost (an external builder) is taken at its word. A run with any call that can
  be priced neither way is reported as unpriced, never guessed.
- **spec drift**: the share of kept evidence records whose findings include
  ``PAC-060``, and the share that failed the gate at all.

A run counts as merged when a commit reachable from ``HEAD`` carries the trailer
``KeelSpec-Run: <run id>``. Cost per merged PR is the cost of *every* run for the
features that merged, failed attempts included, divided by the merged runs.

These are measures of the line, not of the business. They say whether the factory
is healthy; whether the work it ships moves an outcome is measured in production,
against the ``outcome`` each feature traces to. Reporting one as if it were the
other is the mistake this module's name is careful not to make.
"""
from __future__ import annotations

import json
import pathlib
import re
import statistics
import subprocess
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
            data.setdefault("_id", path.stem)
            out.append(data)
    return out


def evidence_dir(root: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(root) / ".keelspec" / "evidence"


def load_evidence(directory: str | pathlib.Path) -> list[dict]:
    """Every readable keelspec evidence record in a directory, oldest first."""
    out = []
    for path in sorted(pathlib.Path(directory).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and str(data.get("schema", "")).startswith("keelspec-evidence/"):
            out.append(data)
    return out


TRAILER = re.compile(r"^KeelSpec-Run:[ \t]*(\S+)[ \t]*$", re.MULTILINE)


def merged_run_ids(root: str | pathlib.Path) -> set[str] | None:
    """Run ids named by a ``KeelSpec-Run:`` trailer on a commit reachable from HEAD.

    None when the root is not a git repository, so "no merges" and "cannot tell"
    stay different answers.
    """
    try:
        proc = subprocess.run(["git", "log", "--format=%B"], cwd=root,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return set(TRAILER.findall(proc.stdout))


def _call_cost(entry: dict, prices: dict) -> float | None:
    if isinstance(entry.get("total_cost_usd"), (int, float)):
        return float(entry["total_cost_usd"])
    price = prices.get(entry.get("model", ""))
    if price is None:
        return None
    if isinstance(price, dict):
        get = price.get
    else:
        def get(key):
            return getattr(price, key, None)
    cost = (entry.get("input_tokens", 0) * get("input_per_mtok")
            + entry.get("output_tokens", 0) * get("output_per_mtok"))
    for key, rate in (("cache_read_input_tokens", "cache_read_per_mtok"),
                      ("cache_creation_input_tokens", "cache_write_per_mtok")):
        if entry.get(key):
            # An unpriced cache rate falls back to the input rate: cache tokens are
            # input tokens, and leaving them out would understate the cost.
            rate_value = get(rate)
            cost += entry[key] * (rate_value if rate_value is not None else get("input_per_mtok"))
    return cost / 1_000_000


def run_cost(run: dict, prices: dict) -> float | None:
    """What one run cost in USD, or None if any of its calls cannot be priced."""
    entries = run.get("usage") or []
    if not entries:
        return None
    costs = [_call_cost(e, prices) for e in entries]
    return None if any(c is None for c in costs) else round(sum(costs), 6)


def _lens_rates(runs: list[dict]) -> tuple[dict, dict]:
    cast: Counter[str] = Counter()
    refuted: Counter[str] = Counter()
    abstained: Counter[str] = Counter()
    for run in runs:
        hit = {lens for t in run.get("triage") or [] for lens in t.get("lenses") or []}
        for v in run.get("verdicts") or []:
            lens = v.get("lens")
            if not lens:
                continue
            # Records from before the flag existed mark an abstention only in prose.
            if v.get("abstained") or str(v.get("reason", "")).startswith("lens inconclusive"):
                abstained[lens] += 1
                continue
            cast[lens] += 1
            if lens in hit or (v.get("refuted") and v.get("severity") in {"blocker", "major"}):
                refuted[lens] += 1
    rates = {lens: round(refuted[lens] / n, 3) for lens, n in sorted(cast.items())}
    return rates, dict(sorted(abstained.items()))


def _review_load(runs: list[dict]) -> dict:
    by_feature: dict[str, dict] = {}
    for run in runs:
        f = by_feature.setdefault(run["feature"], {
            "runs": 0, "needs_human": 0, "blocked": 0, "questions_asked": 0,
            "approvals_given": 0, "approvals_missing": 0})
        f["runs"] += 1
        f["needs_human"] += run.get("status") == "needs-human"
        f["blocked"] += run.get("status") == "blocked"
        gate = next((s for s in run.get("steps") or [] if s.get("station") == "ST-02"), None)
        f["questions_asked"] += len(((gate or {}).get("data") or {}).get("questions") or [])
        # Approvals are standing state, so the latest run's count is the one that holds.
        f["approvals_given"] = len(run.get("approvals") or [])
        f["approvals_missing"] = len(run.get("approvals_missing") or [])
    keys = ("needs_human", "blocked", "questions_asked", "approvals_given", "approvals_missing")
    totals = {k: sum(f[k] for f in by_feature.values()) for k in keys}
    return {**totals, "by_feature": dict(sorted(by_feature.items()))}


def _cost(runs: list[dict], prices: dict, merged: set[str] | None) -> dict:
    costs = {run["_id"]: run_cost(run, prices) for run in runs if run.get("_id")}
    priced = [c for c in costs.values() if c is not None]
    out = {
        "priced_runs": len(priced),
        "unpriced_runs": len(costs) - len(priced),
        "total_usd": round(sum(priced), 4) if priced else None,
        "mean_per_run_usd": round(statistics.mean(priced), 4) if priced else None,
        "merged_runs": None if merged is None else 0,
        "per_merged_pr_usd": None,
    }
    if merged is None:
        return out
    merged_runs = [r for r in runs if r.get("_id") in merged]
    out["merged_runs"] = len(merged_runs)
    features = {r["feature"] for r in merged_runs}
    spent = [costs.get(r.get("_id")) for r in runs if r["feature"] in features]
    if merged_runs and spent and all(c is not None for c in spent):
        out["per_merged_pr_usd"] = round(sum(spent) / len(merged_runs), 4)
    return out


def _drift(records: list[dict] | None) -> dict | None:
    if not records:
        return None
    stale = sum(1 for r in records
                if any(f.get("code") == "PAC-060" for f in r.get("findings") or []))
    failed = sum(1 for r in records if r.get("result") != "pass")
    return {"records": len(records),
            "drift_rate": round(stale / len(records), 3),
            "gate_failure_rate": round(failed / len(records), 3)}


def _seconds(run: dict) -> float | None:
    try:
        start = datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(run["finished_at"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, ValueError):
        return None
    return (end - start).total_seconds()


def summarise(runs: list[dict], *, prices: dict | None = None,
              merged: set[str] | None = None,
              evidence: list[dict] | None = None) -> dict:
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

    rates, abstentions = _lens_rates(runs)
    return {
        "schema": "keelspec-metrics/2",
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
        # keelspec-metrics/2: every /1 field above is unchanged.
        "rejection_rate_by_lens": rates,
        "abstentions_by_lens": abstentions,
        "review_load": _review_load(runs),
        "cost": _cost(runs, prices or {}, merged),
        "drift": _drift(evidence),
    }


def render_text(summary: dict) -> str:
    def pct(x):
        return "n/a" if x is None else f"{x:.0%}"

    def counts(d):
        return ", ".join(f"{k} {v}" for k, v in d.items()) or "none"

    def usd(x):
        return "unknown" if x is None else f"${x:,.2f}"

    rates = ", ".join(f"{k} {pct(v)}" for k, v in summary["rejection_rate_by_lens"].items())
    load, cost, drift = summary["review_load"], summary["cost"], summary["drift"]
    merged = "" if cost["merged_runs"] is None else f" ({cost['merged_runs']} merged run(s))"
    if drift is None:
        drift_line = "no evidence records kept"
    else:
        drift_line = (f"{pct(drift['drift_rate'])} of {drift['records']} evidence record(s) "
                      f"stale (PAC-060); {pct(drift['gate_failure_rate'])} failed the gate")

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
        f"rejection rate by lens: {rates or 'none'}",
        f"abstentions by lens: {counts(summary['abstentions_by_lens'])}",
        f"review load: {load['needs_human']} needs-human run(s), {load['blocked']} blocked, "
        f"{load['questions_asked']} question(s) asked, {load['approvals_given']} approval(s) "
        f"given, {load['approvals_missing']} missing",
        f"cost: {usd(cost['total_usd'])} over {cost['priced_runs']} priced run(s) "
        f"({cost['unpriced_runs']} unpriced)   per merged PR: {usd(cost['per_merged_pr_usd'])}{merged}",
        f"spec drift: {drift_line}",
        "",
        "These measure the line. Business outcomes are measured in production, "
        "against each feature's outcome.",
    ]
    return "\n".join(lines) + "\n"
