"""keelspec-metrics/2: rejection rates, review load, cost per merged PR, spec drift."""
from __future__ import annotations

import json
import subprocess

import pytest

from keelspec import metrics
from keelspec.config import Price
from keelspec.orchestration import Orchestrator, StubRunner, Verdict, save_report


class Metered(StubRunner):
    """A stub that reports token usage the way the real runners do."""

    def run(self, station, prompt, schema=None):
        data = super().run(station, prompt, schema)
        data["_usage"] = {"model": "m-1", "input_tokens": 1000, "output_tokens": 100}
        return data


def test_usage_is_collected_per_call_and_kept_out_of_step_data():
    report = Orchestrator(Metered()).run("FEAT-x")
    assert report.status == "proposed"
    stations = [u["station"] for u in report.usage]
    # Understand, Disambiguate, Design, Develop, Clean, Test, then five critics in parallel.
    assert stations.count("ST-06") == 5
    assert {"ST-01", "ST-03", "ST-04", "ST-05"} <= set(stations)
    assert all("_usage" not in s.data for s in report.steps)
    assert report.to_dict()["usage"][0]["model"] == "m-1"


def test_a_run_without_usage_keeps_its_old_shape():
    assert "usage" not in Orchestrator(StubRunner()).run("FEAT-x").to_dict()


def test_an_abstaining_critic_is_flagged():
    assert Verdict.benign("security", "timeout").abstained is True
    assert Verdict("security", False, "none", "fine").abstained is False


def _run(feature, status="proposed", verdicts=(), triage=(), usage=(), questions=0,
         approvals=0, missing=0, rid=None):
    return {"_id": rid or f"{feature}-{status}", "feature": feature, "status": status,
            "verdicts": list(verdicts), "triage": list(triage), "usage": list(usage),
            "steps": [{"station": "ST-02", "data": {"questions": [{}] * questions}}],
            "approvals": [{}] * approvals, "approvals_missing": ["x"] * missing}


V = lambda lens, refuted=False, **kw: {"lens": lens, "refuted": refuted,  # noqa: E731
                                        "severity": "major" if refuted else "none",
                                        "reason": kw.get("reason", "r"), **kw}


def test_rejection_rate_counts_any_round_and_excludes_abstentions():
    runs = [
        _run("FEAT-a", verdicts=[V("security"), V("coverage")],
             triage=[{"lenses": ["security"], "cause": "implementation"}]),   # refuted, then fixed
        _run("FEAT-b", verdicts=[V("security"), V("coverage", refuted=True)]),
        _run("FEAT-c", verdicts=[V("security", abstained=True),
                                 V("coverage", reason="lens inconclusive (timeout); ...")]),
    ]
    s = metrics.summarise(runs)
    assert s["schema"] == "keelspec-metrics/2"
    assert s["rejection_rate_by_lens"] == {"coverage": 0.5, "security": 0.5}
    assert s["abstentions_by_lens"] == {"coverage": 1, "security": 1}


def test_review_load_adds_up_what_the_line_asked_of_people():
    runs = [_run("FEAT-a", status="blocked", questions=3, missing=1, rid="a1"),
            _run("FEAT-a", status="needs-human", questions=3, approvals=1, rid="a2"),
            _run("FEAT-b", questions=0)]
    load = metrics.summarise(runs)["review_load"]
    assert (load["needs_human"], load["blocked"], load["questions_asked"]) == (1, 1, 6)
    assert load["by_feature"]["FEAT-a"]["approvals_given"] == 1        # the latest state holds
    assert load["by_feature"]["FEAT-a"]["approvals_missing"] == 0


def test_cost_needs_a_price_or_a_vendor_figure_and_never_guesses():
    priced = {"m-1": Price(input_per_mtok=3.0, output_per_mtok=15.0)}
    call = {"model": "m-1", "input_tokens": 1_000_000, "output_tokens": 100_000}
    vendor = {"model": "claude-code", "total_cost_usd": 0.25}
    runs = [_run("FEAT-a", usage=[call, vendor], rid="a"),
            _run("FEAT-b", usage=[{"model": "unknown", "input_tokens": 5}], rid="b")]

    cost = metrics.summarise(runs, prices=priced)["cost"]
    assert cost["priced_runs"] == 1 and cost["unpriced_runs"] == 1
    assert cost["total_usd"] == pytest.approx(3.0 + 1.5 + 0.25)

    # Without a price table, run a has one call nobody priced, so the whole run is
    # unpriced: a partial total would understate it.
    unpriced = metrics.summarise(runs)["cost"]
    assert unpriced["priced_runs"] == 0 and unpriced["total_usd"] is None


def test_cache_tokens_fall_back_to_the_input_rate():
    price = {"m": Price(input_per_mtok=2.0, output_per_mtok=0.0)}
    run = {"usage": [{"model": "m", "cache_read_input_tokens": 1_000_000}]}
    assert metrics.run_cost(run, price) == pytest.approx(2.0)


def test_cost_per_merged_pr_includes_the_failed_attempts(tmp_path):
    price = {"m": Price(input_per_mtok=1.0, output_per_mtok=0.0)}
    one = [{"model": "m", "input_tokens": 1_000_000}]                       # $1 per run
    runs = [_run("FEAT-a", status="refuted", usage=one, rid="FEAT-a-1"),
            _run("FEAT-a", usage=one, rid="FEAT-a-2"),
            _run("FEAT-b", usage=one, rid="FEAT-b-1")]                       # never merged
    cost = metrics.summarise(runs, prices=price, merged={"FEAT-a-2"})["cost"]
    assert cost["merged_runs"] == 1
    assert cost["per_merged_pr_usd"] == pytest.approx(2.0)


def test_merged_runs_are_found_by_commit_trailer(tmp_path):
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m",
                    "feat: refunds\n\nKeelSpec-Run: FEAT-a-20261122T100000Z"],
                   cwd=tmp_path, check=True)
    assert metrics.merged_run_ids(tmp_path) == {"FEAT-a-20261122T100000Z"}
    assert metrics.merged_run_ids(tmp_path / "nowhere") is None


def test_drift_rate_comes_from_kept_evidence_records(tmp_path):
    ev = tmp_path / "ev"
    ev.mkdir()
    records = [{"result": "pass", "findings": []},
               {"result": "fail", "findings": [{"code": "PAC-060"}]},
               {"result": "fail", "findings": [{"code": "PAC-020"}]},
               {"result": "pass", "findings": []}]
    for i, r in enumerate(records):
        (ev / f"{i}.json").write_text(json.dumps({"schema": "keelspec-evidence/1", **r}))
    (ev / "other.json").write_text(json.dumps({"schema": "something-else"}))
    drift = metrics.summarise([], evidence=metrics.load_evidence(ev))["drift"]
    assert drift == {"records": 4, "drift_rate": 0.25, "gate_failure_rate": 0.5}
    assert metrics.summarise([])["drift"] is None


def test_cli_reports_v2_from_kept_runs_prices_and_evidence(tmp_path, capsys):
    from keelspec.cli import main
    (tmp_path / "product.config.yaml").write_text(
        "types: []\nprices:\n  m-1: {input_per_mtok: 3, output_per_mtok: 15}\n")
    save_report(tmp_path, Orchestrator(Metered()).run("FEAT-a"))
    ev = tmp_path / ".keelspec" / "evidence"
    ev.mkdir(parents=True)
    (ev / "1.json").write_text(json.dumps({"schema": "keelspec-evidence/1",
                                           "result": "pass", "findings": []}))
    assert main(["-C", str(tmp_path), "runs", "--json"]) == 0
    s = json.loads(capsys.readouterr().out)
    assert s["schema"] == "keelspec-metrics/2"
    assert s["cost"]["priced_runs"] == 1 and s["cost"]["total_usd"] > 0
    assert s["drift"]["records"] == 1
    assert s["cost"]["merged_runs"] is None                  # not a git repo: cannot tell
    assert main(["-C", str(tmp_path), "runs"]) == 0
    text = capsys.readouterr().out
    assert "rejection rate by lens" in text and "per merged PR: unknown" in text
