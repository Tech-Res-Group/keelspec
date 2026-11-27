"""v2 M11: agent-aware orchestration -- the policy lens and ST-04c Tools."""
from __future__ import annotations

import copy
import json
import shutil

import pytest
from test_runtime import AGENT, EXAMPLE

from keelspec.cli import main
from keelspec.config import load_config
from keelspec.engine import load
from keelspec.orchestration import Orchestrator, StubRunner
from keelspec.runtime.policy import AgentPolicies
from keelspec.runtime.policy_lens import (
    MISSING,
    _values,
    candidate_args,
    find_bypass,
    forbidden_operations,
    policy_lens,
    probe_injection,
)
from keelspec.runtime.scaffold import scaffold, server_module, tool_gaps

CASES = "TOOL-case-management"


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "ex"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def _bundle(root=EXAMPLE) -> dict:
    return load(load_config(root / "product.config.yaml"), root)


def _with_policy(bundle: dict, pol: dict, drop: str | None = None) -> dict:
    b = copy.deepcopy(bundle)
    b["policies"] = [p for p in b["policies"] if p["id"] != drop] + [pol]
    agent = b["agents"][0]
    agent["policies"] = [p for p in agent["policies"] if p != drop] + [pol["id"]]
    return b


# ── the argument search ──────────────────────────────────────────────────────
@pytest.mark.parametrize("cond,expected", [
    ({"op": ">", "value": 0}, [MISSING, -1, 0, 1, 0, -1, "0"]),
    ({"op": "in", "value": ["EUR", "GBP"]}, [MISSING, "EUR", "GBP", "zz-not-in-the-list"]),
    ({"op": "exists"}, [MISSING, "present"]),
    ({"op": "matches", "value": "^X"}, [MISSING, "", "x", "^X"]),
    ({"op": "==", "value": True}, [MISSING, True, False]),
    ({"op": "==", "value": "ops"}, [MISSING, "ops", "ops-other", None]),
    ({"op": "==", "value": None}, [MISSING, None, "other", None]),
])
def test_boundary_values(cond, expected):
    assert _values(cond) == expected


def test_candidate_args_cover_nested_paths_and_combinations():
    bundle = _with_policy(_bundle(), {
        "id": "POL-x", "effect": "deny", "match": {"tool": CASES, "operation": "add_comment"},
        "when": [{"arg": "meta.channel", "op": "in", "value": ["email"]},
                 {"arg": "urgent", "op": "==", "value": True}]})
    ap = AgentPolicies.from_bundle(bundle, AGENT)
    cands = candidate_args(ap, CASES, "add_comment")
    assert {} in cands and {"__unparseable__": True} in cands
    assert {"meta": {"channel": "email"}, "urgent": True} in cands
    assert {"meta": {"channel": "zz-not-in-the-list"}} in cands
    assert {"urgent": False} in cands
    assert len(cands) == len({json.dumps(c, sort_keys=True) for c in cands})


def test_forbidden_operations_of_the_example():
    ap = AgentPolicies.from_bundle(_bundle(), AGENT)
    assert forbidden_operations(ap) == [(CASES, "propose_repair"), (CASES, "release_funds")]
    assert find_bypass(ap, CASES, "propose_repair") is None
    assert find_bypass(ap, CASES, "release_funds") is None


def test_the_example_has_no_path_to_a_forbidden_call():
    verdict = policy_lens(_bundle(), AGENT)
    assert verdict["lens"] == "policy" and verdict["refuted"] is False
    assert "2 guarded or money operation(s)" in verdict["reason"]
    assert "3 scenario(s)" in verdict["reason"]


def test_a_blanket_allow_opens_a_bypass_round_the_approval():
    """POL-repair-needs-approval only fires for amount_minor > 0. Add a blanket
    allow on the case tool and a negative or zero amount walks straight through."""
    bundle = _with_policy(_bundle(), {"id": "POL-allow-case-writes", "effect": "allow",
                                      "match": {"tool": CASES}})
    verdict = policy_lens(bundle, AGENT)
    assert verdict["refuted"] and verdict["severity"] == "blocker"
    assert "propose_repair is guarded by policy but runs unattended" in verdict["reason"]
    assert '"amount_minor": -1' in verdict["failing_case"]


def test_unguarded_money_and_injection_are_found():
    bundle = _with_policy(_bundle(), {"id": "POL-allow-release", "effect": "allow",
                                      "match": {"tool": CASES, "operation": "release_funds"}},
                          drop="POL-no-funds-movement")
    verdict = policy_lens(bundle, AGENT)
    assert verdict["refuted"] and verdict["severity"] == "blocker"   # high criticality
    assert "release_funds moves money and runs unattended" in verdict["reason"]
    assert "can be triggered by text in tool results" in verdict["reason"]
    assert "scenario SCN-prompt-injection-in-remittance fails" in verdict["reason"]

    bundle["agents"][0]["criticality"] = "normal"
    assert policy_lens(bundle, AGENT)["severity"] == "blocker"       # the probe still is


def test_probe_without_scenarios_uses_a_synthetic_case():
    bundle = _with_policy(_bundle(), {"id": "POL-allow-release", "effect": "allow",
                                      "match": {"tool": CASES, "operation": "release_funds"}},
                          drop="POL-no-funds-movement")
    bundle["agents"][0]["scenarios"] = []
    bundle["scenarios"] = []
    case = probe_injection(bundle, AGENT, CASES, "release_funds")
    assert case and "made TOOL-case-management.release_funds run" in case
    assert probe_injection(_bundle(), AGENT, CASES, "release_funds") is None


# ── the orchestrator, on the StubRunner path ─────────────────────────────────
def _orchestrate(lens, tools=None):
    return Orchestrator(StubRunner(), deterministic_lenses={"policy": lens},
                        tools_station=tools).run(AGENT)


def test_orchestrator_report_carries_the_policy_verdict():
    gaps = {"servers_missing": [], "generated": [], "notes": [],
            "fixtures_missing": ["SCN-x: must_call T.o has no fixture"]}
    report = _orchestrate(lambda: policy_lens(_bundle(), AGENT), lambda: gaps)
    assert report.status == "proposed"
    (verdict,) = [v for v in report.verdicts if v.lens == "policy"]
    assert not verdict.refuted
    stations = [s.station for s in report.steps]
    assert stations.index("ST-04c") == stations.index("ST-04") + 1
    assert "missing fixture: SCN-x: must_call T.o has no fixture" in report.notes


def test_a_refuting_policy_lens_blocks_the_line():
    bad = _with_policy(_bundle(), {"id": "POL-allow-case-writes", "effect": "allow",
                                   "match": {"tool": CASES}})
    report = _orchestrate(lambda: policy_lens(bad, AGENT))
    assert report.status == "refuted"
    assert [v.lens for v in report.blocking] == ["policy"]
    assert report.triage and report.triage[0]["lenses"] == ["policy"]


def test_a_lens_that_crashes_fails_closed_and_a_broken_tools_station_does_not_stop():
    def boom():
        raise RuntimeError("no bundle")

    def broken():
        raise FileExistsError("would overwrite")
    report = _orchestrate(boom, broken)
    (verdict,) = [v for v in report.verdicts if v.lens == "policy"]
    assert verdict.refuted and verdict.severity == "major"
    assert "lens could not run: no bundle" in verdict.reason
    assert "Tools could not run: would overwrite" in report.notes
    assert report.status == "refuted"


# ── ST-04c Tools ─────────────────────────────────────────────────────────────
def test_server_module():
    assert server_module({"server": {"command": "python",
                                     "args": ["-m", "servers.x"]}}) == "servers.x"
    assert server_module({"transport": "http", "server": {"url": "u"}}) is None
    assert server_module({"server": {"command": "node", "args": ["srv.js"]}}) is None
    assert server_module({"server": {"args": ["-m"]}}) is None


def test_tool_gaps_finds_and_scaffolds_missing_servers(project):
    assert tool_gaps(_bundle(project), AGENT, project) == {
        "servers_missing": [], "generated": [], "fixtures_missing": [], "notes": []}
    shutil.rmtree(project / "servers" / "case_management")
    dry = tool_gaps(_bundle(project), AGENT, project)
    assert dry["servers_missing"] == [{"tool": CASES, "module": "servers.case_management"}]
    assert dry["generated"] == [] and not (project / "servers" / "case_management").exists()
    wet = tool_gaps(_bundle(project), AGENT, project, write=True)
    assert "servers/case_management/server.py" in wet["generated"]
    test_src = (project / "servers" / "case_management" / "test_server.py").read_text()
    assert "from servers.case_management.server import server" in test_src


def test_tool_gaps_notes_and_fixtures(project):
    bundle = _bundle(project)
    tools = {t["id"]: t for t in bundle["tools"]}
    tools["TOOL-payments-ledger"]["transport"] = "http"
    tools["TOOL-iso20022-parser"]["server"] = {"command": "node", "args": ["parser.js"]}
    scn = next(s for s in bundle["scenarios"] if s["id"] == "SCN-duplicate-submission")
    del scn["fixtures"]["TOOL-payments-ledger.list_postings"]
    gaps = tool_gaps(bundle, AGENT, project)
    assert gaps["notes"] == [
        "TOOL-payments-ledger is served over HTTP; nothing to generate here",
        "TOOL-iso20022-parser does not run as a Python module; not generated"]
    assert gaps["fixtures_missing"] == [
        "SCN-duplicate-submission: must_call TOOL-payments-ledger.list_postings has no fixture"]
    bundle["agents"][0]["scenarios"] = []
    bundle["scenarios"] = []
    assert tool_gaps(bundle, AGENT, project)["fixtures_missing"] == [f"{AGENT} has no scenarios"]
    with pytest.raises(KeyError):
        tool_gaps(bundle, "AGENT-nope", project)


def test_scaffold_into_the_project_root_adds_no_root_package(tmp_path):
    files = scaffold({"id": "TOOL-t", "operations": [{"name": "a"}]}, tmp_path,
                     out_dir=".", package="tserver")
    assert not (tmp_path / "__init__.py").exists()
    assert "from tserver.server import server" in (tmp_path / "tserver" / "test_server.py").read_text()
    assert len(files) == 4


# ── the CLI: dry-run on the example ──────────────────────────────────────────
def test_orchestrate_agent_dry_run(project, capsys):
    shutil.rmtree(project / "servers" / "payments_ledger")
    assert main(["-C", str(project), "orchestrate", AGENT, "--dry-run", "--write",
                 "-o", "out/report.json"]) == 0
    err = capsys.readouterr().err
    assert "ST-04c Tools and the policy lens join the line" in err
    report = json.loads((project / "out" / "report.json").read_text())
    assert report["status"] == "proposed"
    (policy,) = [v for v in report["verdicts"] if v["lens"] == "policy"]
    assert policy["refuted"] is False
    tools = next(s for s in report["steps"] if s["station"] == "ST-04c")
    assert tools["data"]["servers_missing"] == [{"tool": "TOOL-payments-ledger",
                                                 "module": "servers.payments_ledger"}]
    assert tools["data"]["generated"] == []                  # a dry run writes nothing
    assert not (project / "servers" / "payments_ledger").exists()


def test_orchestrate_a_feature_has_no_agent_stations(project, capsys):
    (project / "product" / "rules" / "BR-idempotent.md").exists()
    assert main(["-C", str(project), "orchestrate", "BR-idempotent", "--dry-run",
                 "-o", "out/r.json"]) == 0
    report = json.loads((project / "out" / "r.json").read_text())
    assert "ST-04c" not in [s["station"] for s in report["steps"]]
    assert "policy" not in [v["lens"] for v in report["verdicts"]]
