"""Accountability on the line: risk tiers, named approvers, triage, and run metrics.

Each of these answers a question a business stakeholder asked of the line and the
line could not answer: who accepted this spec, in what role? Why did this change get
the light path? When it failed twice, was the code wrong, or the requirement? Is the
factory getting better?
"""
from __future__ import annotations

import json
import pathlib

import pytest
import yaml

from keelspec import validate
from keelspec.config import ArtifactType, Config, Delivery, RiskTier
from keelspec.orchestration import (
    TRIAGE_SCHEMA,
    Orchestrator,
    StubRunner,
    read_approvals,
    read_resolutions,
    save_report,
    write_questions,
)
from keelspec.risk import assess

REFUTING = {"security": {"lens": "security", "refuted": True, "severity": "blocker",
                         "reason": "no authz", "failing_case": "anonymous POST"}}


def _delivery() -> Delivery:
    return Delivery.model_validate({
        "risk_factors": {"customer_impact": {"high": 3, "medium": 1},
                         "data": {"pii": 3},
                         "reversible": {False: 3}},
        "tiers": [
            {"name": "light", "min_score": 0, "lenses": ["correctness"], "clean": False,
             "max_repair": 0},
            {"name": "high", "min_score": 5, "approvers": ["product-owner", "security"]},
            {"name": "standard", "min_score": 2, "approvers": ["product-owner"]},
        ],
    })


# ── PAC-002: recommended fields warn, never gate ─────────────────────────────
def test_a_missing_recommended_field_warns_but_does_not_gate(tmp_path):
    cfg = Config(types=[ArtifactType(name="features", dir="features", id_prefix="FEAT-",
                                     fields=["outcome"], recommended=["outcome"])])
    d = tmp_path / "product" / "features"
    d.mkdir(parents=True)
    (d / "FEAT-a.md").write_text("---\nid: FEAT-a\n---\nbody", encoding="utf-8")
    from keelspec import build
    build(cfg, tmp_path)

    report = validate(cfg, tmp_path)
    assert report.ok
    assert [(w.code, w.field) for w in report.warnings] == [("PAC-002", "outcome")]


# ── risk tiers ───────────────────────────────────────────────────────────────
def test_unquoted_yaml_booleans_are_matchable_factor_values():
    """`reversible: {false: 3}` must work without the author quoting `false`."""
    delivery = Delivery.model_validate(yaml.safe_load(
        "risk_factors:\n  reversible: {false: 3}\ntiers: []\n"))
    assert delivery.risk_factors == {"reversible": {"false": 3}}


@pytest.mark.parametrize("record, tier, score", [
    ({"customer_impact": "low"}, "light", 0),
    ({"customer_impact": "medium", "data": "pii"}, "standard", 4),
    ({"customer_impact": "high", "reversible": False}, "high", 6),
    ({"data": ["pii", "internal"]}, "standard", 3),       # list values each count
])
def test_the_score_picks_the_highest_tier_it_reaches(record, tier, score):
    a = assess(_delivery(), record)
    assert (a.tier.name, a.score) == (tier, score)


def test_the_assessment_says_why():
    a = assess(_delivery(), {"customer_impact": "high", "reversible": False})
    assert a.reasons == ("customer_impact=high (+3)", "reversible=false (+3)")


def test_an_artifact_that_cannot_be_found_gets_the_highest_tier():
    """Not knowing the risk of a change is not evidence that it is low."""
    a = assess(_delivery(), None)
    assert a.tier.name == "high"


def test_no_delivery_policy_means_the_default_line():
    a = assess(None, {"customer_impact": "high"})
    assert a.tier is None
    assert a.orchestrator_options() == {"risk": {"score": 0, "tier": "", "reasons": []}}


def test_a_tier_only_overrides_what_it_states():
    opts = assess(_delivery(), {"customer_impact": "high", "data": "pii"}).orchestrator_options()
    assert opts["required_approvers"] == ["product-owner", "security"]
    assert "lenses" not in opts and "clean" not in opts and "max_repair" not in opts


def test_a_light_tier_runs_its_own_lenses_and_skips_clean():
    opts = assess(_delivery(), {}).orchestrator_options()
    runner = StubRunner()
    report = Orchestrator(runner, **opts).run("FEAT-x")
    assert [v.lens for v in report.verdicts] == ["correctness"]
    assert "ST-04b" not in [s.station for s in report.steps]
    assert report.risk["tier"] == "light"


def test_a_misspelt_lens_is_refused_rather_than_silently_skipped():
    with pytest.raises(ValueError, match="secruity"):
        Orchestrator(StubRunner(), lenses=["correctness", "secruity"])


def test_tier_names_and_lens_lists_round_trip_through_config():
    tier = RiskTier(name="x", lenses=["integrity"])
    Orchestrator(StubRunner(), lenses=tier.lenses)       # integrity is a real lens


# ── named approvers at the human gate ────────────────────────────────────────
def test_required_approvers_block_design_until_each_role_signs():
    report = Orchestrator(StubRunner(),
                          required_approvers=["product-owner", "security"],
                          approvals=[{"role": "product-owner", "by": "Avery", "at": ""}],
                          ).run("FEAT-x")
    assert report.status == "blocked"
    assert report.approvals_missing == ["security"]
    assert "ST-03" not in [s.station for s in report.steps]


def test_approvals_are_recorded_on_the_report():
    signed = [{"role": "product-owner", "by": "Avery", "at": "2026-10-04T09:00:00Z"}]
    report = Orchestrator(StubRunner(), required_approvers=["product-owner"],
                          approvals=signed).run("FEAT-x")
    assert report.status == "proposed"
    assert report.approvals == signed
    assert report.to_dict()["approvals"] == signed


def test_an_autonomous_run_cannot_skip_a_required_approver():
    """Open questions can be advisory; who must accept the spec cannot."""
    report = Orchestrator(StubRunner(), required_approvers=["product-owner"]).run(
        "FEAT-x", block_on_unresolved=False)
    assert report.status == "blocked"
    assert report.approvals_missing == ["product-owner"]


def test_an_unsigned_slot_is_not_an_approval():
    report = Orchestrator(StubRunner(), required_approvers=["product-owner"],
                          approvals=[{"role": "product-owner", "by": "", "at": ""}]
                          ).run("FEAT-x")
    assert report.approvals_missing == ["product-owner"]


def test_the_gate_file_carries_approval_slots_and_keeps_what_was_signed(tmp_path):
    questions = [{"id": "q1", "dimension": "window", "question": "From when?"}]
    path = write_questions(tmp_path, "FEAT-x", questions,
                           required_roles=["product-owner", "security"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [a["role"] for a in payload["approvals"]] == ["product-owner", "security"]
    assert read_approvals(tmp_path, "FEAT-x") == []          # empty slots sign nothing

    payload["approvals"][0]["by"] = "Avery"
    payload["questions"][0]["answer"] = "from settlement"
    path.write_text(json.dumps(payload), encoding="utf-8")

    write_questions(tmp_path, "FEAT-x", questions, required_roles=["product-owner", "security"])
    assert read_approvals(tmp_path, "FEAT-x") == [
        {"role": "product-owner", "by": "Avery", "at": ""}]
    assert read_resolutions(tmp_path, "FEAT-x")["q1"] == "from settlement"


# ── triage before repair ─────────────────────────────────────────────────────
def test_a_requirement_fault_goes_to_a_person_not_back_to_the_developer():
    triage = {"cause": "requirement", "reasoning": "AC2 contradicts AC4",
              "ask": "Which wins: the refund window or the chargeback rule?"}
    report = Orchestrator(StubRunner(verdicts=REFUTING, triage=triage)).run("FEAT-x")

    assert report.status == "needs-human"
    assert report.repair_rounds == 0                     # nobody retried it
    assert report.triage == [{"round": 0, "lenses": ["security"], **triage}]
    assert any("Which wins" in n for n in report.notes)


def test_an_implementation_fault_is_repaired_as_before():
    report = Orchestrator(StubRunner(verdicts=REFUTING)).run("FEAT-x")
    assert report.status == "refuted"
    assert report.repair_rounds == 2
    # triaged before each repair, and once more when the rounds ran out
    assert [t["round"] for t in report.triage] == [0, 1, 2]


def test_an_unreachable_triage_falls_back_to_repair():
    class NoTriage(StubRunner):
        def run(self, station, prompt, schema=None):
            if schema is TRIAGE_SCHEMA:
                raise RuntimeError("provider down")
            return super().run(station, prompt, schema)

    report = Orchestrator(NoTriage(verdicts=REFUTING), max_repair=1).run("FEAT-x")
    assert report.status == "refuted"
    assert report.repair_rounds == 1
    assert "inconclusive" in report.triage[0]["reasoning"]


def test_a_clean_run_is_never_triaged():
    report = Orchestrator(StubRunner()).run("FEAT-x")
    assert report.triage == []


def test_runs_are_timestamped():
    report = Orchestrator(StubRunner()).run("FEAT-x")
    assert report.started_at and report.finished_at >= report.started_at


# ── metrics ──────────────────────────────────────────────────────────────────
def test_runs_add_up_into_line_metrics(tmp_path):
    from keelspec import metrics

    save_report(tmp_path, Orchestrator(StubRunner()).run("FEAT-a"))
    save_report(tmp_path, Orchestrator(StubRunner(verdicts=REFUTING), max_repair=1).run("FEAT-b"))
    save_report(tmp_path, Orchestrator(
        StubRunner(verdicts=REFUTING, triage={"cause": "design", "reasoning": "r"})).run("FEAT-c"))
    (metrics.runs_dir(tmp_path) / "junk.json").write_text("{not json", encoding="utf-8")

    s = metrics.summarise(metrics.load_runs(tmp_path))
    assert s["runs"] == 3 and s["features"] == 3
    assert s["status"] == {"needs-human": 1, "proposed": 1, "refuted": 1}
    assert s["first_pass_rate"] == pytest.approx(1 / 3, abs=0.001)
    assert s["refuted_by_lens"] == {"security": 2}
    assert s["triage_causes"] == {"design": 1, "implementation": 2}
    assert "measure the line" in metrics.render_text(s)


def test_cli_runs_with_no_history_is_not_an_error(tmp_path, capsys):
    from keelspec.cli import main
    (tmp_path / "product.config.yaml").write_text("types: []\n", encoding="utf-8")
    assert main(["-C", str(tmp_path), "runs", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["runs"] == 0


# ── the CLI applies the tier and takes approvals ─────────────────────────────
def _tiered_project(tmp_path: pathlib.Path, impact: str) -> pathlib.Path:
    (tmp_path / "product.config.yaml").write_text(yaml.safe_dump({
        "types": [{"name": "features", "dir": "features", "id_prefix": "FEAT-",
                   "fields": ["customer_impact"]}],
        "delivery": {"risk_factors": {"customer_impact": {"high": 5}},
                     "tiers": [{"name": "high", "min_score": 5,
                                "approvers": ["product-owner"]},
                               {"name": "light", "min_score": 0,
                                "lenses": ["correctness", "coverage"]}]},
    }), encoding="utf-8")
    d = tmp_path / "product" / "features"
    d.mkdir(parents=True)
    (d / "FEAT-x.md").write_text(f"---\nid: FEAT-x\ncustomer_impact: {impact}\n---\n",
                                 encoding="utf-8")
    return tmp_path


def test_cli_a_high_tier_feature_waits_for_its_approver(tmp_path, capsys):
    from keelspec.cli import main
    root = _tiered_project(tmp_path, "high")

    assert main(["-C", str(root), "orchestrate", "FEAT-x", "--dry-run"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "blocked"
    assert report["risk"]["tier"] == "high"
    gate = json.loads((root / ".keelspec" / "disambiguations" / "FEAT-x.json")
                      .read_text(encoding="utf-8"))
    assert gate["approvals"] == [{"role": "product-owner", "by": "", "at": ""}]

    assert main(["-C", str(root), "orchestrate", "FEAT-x", "--dry-run",
                 "--approve", "product-owner=Avery Chen"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "proposed"
    assert report["approvals"][0]["by"] == "Avery Chen"
    assert report["approvals"][0]["at"]                   # stamped when given inline


def test_cli_a_light_tier_feature_runs_the_light_lenses(tmp_path, capsys):
    from keelspec.cli import main
    root = _tiered_project(tmp_path, "low")
    assert main(["-C", str(root), "orchestrate", "FEAT-x", "--dry-run"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert [v["lens"] for v in report["verdicts"]] == ["correctness", "coverage"]


def test_cli_rejects_a_malformed_approve_flag(tmp_path, capsys):
    from keelspec.cli import main
    root = _tiered_project(tmp_path, "low")
    assert main(["-C", str(root), "orchestrate", "FEAT-x", "--dry-run",
                 "--approve", "product-owner"]) == 2


def test_product_context_reaches_native_lenses_but_not_the_third_party():
    seen = {}

    def cross(context: str) -> dict:
        seen["cross"] = context
        return {"lens": "cross", "refuted": False, "severity": "none", "reason": "ok"}

    class Capture(StubRunner):
        def run(self, station, prompt, schema=None):
            if station.id == "ST-06":
                seen.setdefault("native", []).append(prompt)
            return super().run(station, prompt, schema)

    Orchestrator(Capture(), brief="RULE: refunds never exceed capture",
                 extra_lens=cross).run("FEAT-x")
    assert "never exceed capture" not in seen["cross"]
    assert all("never exceed capture" in p for p in seen["native"])
