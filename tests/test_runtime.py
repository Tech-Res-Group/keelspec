"""v2 M7: the runtime core -- router client, agent loop, budgets, records, approvals.

Offline: the router is httpx.MockTransport scripted per test, and tools answer from
the example's scenario fixtures. No real FifeRouter, no real model.
"""
from __future__ import annotations

import ast
import json
import pathlib
import shutil

import httpx
import pytest

from keelspec.config import load_config
from keelspec.runtime import approvals, records
from keelspec.runtime.agent import ApprovalPending, resume_agent, run_agent
from keelspec.runtime.bundle import BundleRefused, load_bundle
from keelspec.runtime.fixtures import FixtureExecutor
from keelspec.runtime.router_client import (
    RouterClient,
    RouterSettings,
    RuntimeSettings,
    parse_tool_name,
    to_openai_tool,
    tool_name,
)

REPO = pathlib.Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "examples" / "payments-exceptions"
AGENT = "AGENT-payment-exceptions"
SECRET_INPUT = "Case 88121: pacs.002 RJCT AC04 on E2E-77F (zebra-input-7731)"


class FakeRouter:
    """A scripted FifeRouter. Each reply is a message dict, or an int status."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = self.replies.pop(0) if self.replies else {"content": "done"}
        if isinstance(reply, int):
            return httpx.Response(reply, text="refused")
        return httpx.Response(
            200, json={"model": "claude-x", "choices": [{"message": reply}],
                       "usage": {"prompt_tokens": 100, "completion_tokens": 20}},
            headers={"x-fife-model": "claude-x", "x-fife-rung": "1",
                     "x-fife-attempts": "1", "x-fife-concept": "moneypath.verify"})

    def bodies(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests]


def call(tool: str, op: str, args: dict | None = None, cid: str = "c1") -> dict:
    return {"content": None, "tool_calls": [{"id": cid, "type": "function", "function": {
        "name": tool_name(tool, op), "arguments": json.dumps(args or {})}}]}


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "ex"
    shutil.copytree(EXAMPLE, root)
    return root


def _run(root, fake, text=SECRET_INPUT, scenario="SCN-ac04-closed-account", capture=False,
         **extra):
    cfg = load_config(root / "product.config.yaml")
    bundle, prov = load_bundle(cfg, root)
    router = RouterClient(RouterSettings(base_url="https://router.test/v1"), api_key="k",
                          transport=httpx.MockTransport(fake), sleep=lambda s: None)
    kw = {"root": root, "router": router,
          "executor": FixtureExecutor.from_scenario(bundle, scenario),
          "settings": RuntimeSettings(capture_content=capture)}
    resume = extra.pop("resume", None)
    if resume:
        return resume_agent(bundle, prov, resume, **kw)
    return run_agent(bundle, prov, AGENT, text, **kw, **extra)


# ── I-7: FifeRouter is a service, never an import ────────────────────────────
def test_no_fiferouter_import():
    for base in (REPO / "keelspec", REPO / "tests"):
        for path in base.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                         [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                assert not any(n.split(".")[0] == "fiferouter" for n in names), path


# ── a completed run ──────────────────────────────────────────────────────────
def test_a_run_completes_against_a_mocked_router(project):
    fake = FakeRouter(call("TOOL-case-management", "get_case", {"case_id": "88121"}),
                      call("TOOL-iso20022-parser", "explain_status", {"code": "AC04"}),
                      {"content": "AC04: the creditor account is closed. Return the payment."})
    result = _run(project, fake)
    rec = result.record
    assert rec.outcome == "completed" and "AC04" in result.final_answer
    kinds = [s.kind for s in rec.steps]
    assert kinds == ["model", "policy", "tool", "model", "policy", "tool", "model"]
    model = rec.steps[0]
    assert (model.served_model, model.router_rung, model.router_attempts) == ("claude-x", "1", 1)
    assert dict(rec.budgets_used)["steps"] == 3
    # The ledger's pii fields are masked before the model sees them.
    assert rec.steps[1].policy_effect == "redact"


def test_headers_carry_concept_session_criticality_and_trace(project):
    fake = FakeRouter({"content": "nothing to do"})
    rec = _run(project, fake).record
    h = fake.requests[0].headers
    assert h["x-fife-concept"] == "moneypath.verify"
    assert h["x-fife-session"] == rec.run_id
    assert h["x-fife-critical"] == "true"                 # criticality: high
    assert h["authorization"] == "Bearer k"


def test_traceparent_propagated(project):
    fake = FakeRouter(call("TOOL-iso20022-parser", "explain_status", {"code": "AC04"}),
                      {"content": "ok"})
    _run(project, fake)
    tps = [r.headers["traceparent"] for r in fake.requests]
    assert len(set(tps)) == 1                              # one trace for the whole run
    version, trace, span, flags = tps[0].split("-")
    assert (version, len(trace), len(span), flags) == ("00", 32, 16, "01")


# ── I-6: only permitted tools reach the model, and policy gates every call ───
def test_undeclared_tool_never_offered(project):
    fake = FakeRouter({"content": "ok"})
    _run(project, fake)
    offered = {f["function"]["name"] for f in fake.bodies()[0]["tools"]}
    declared = {tool_name(t, o) for t, o in [
        ("TOOL-payments-ledger", "get_payment"), ("TOOL-payments-ledger", "list_postings"),
        ("TOOL-iso20022-parser", "parse_message"), ("TOOL-iso20022-parser", "explain_status"),
        ("TOOL-case-management", "get_case"), ("TOOL-case-management", "add_comment"),
        ("TOOL-case-management", "propose_repair"), ("TOOL-case-management", "release_funds")]}
    assert offered == declared


def test_a_denied_call_never_executes_and_the_model_is_told(project):
    fake = FakeRouter(call("TOOL-case-management", "release_funds", {"amount_minor": 9}),
                      {"content": "I cannot release funds."})
    cfg = load_config(project / "product.config.yaml")
    bundle, prov = load_bundle(cfg, project)
    executor = FixtureExecutor({"TOOL-case-management.release_funds": {"ok": True}})
    router = RouterClient(RouterSettings(base_url="https://router.test/v1"),
                          transport=httpx.MockTransport(fake), sleep=lambda s: None)
    rec = run_agent(bundle, prov, AGENT, "go", root=project, router=router, executor=executor,
                    settings=RuntimeSettings()).record
    assert executor.calls == []
    policy = next(s for s in rec.steps if s.kind == "policy")
    assert policy.policy_effect == "deny" and policy.policy_ids == ("POL-no-funds-movement",)
    tool_msg = fake.bodies()[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and "denied by policy" in tool_msg["content"]
    assert rec.outcome == "completed"


def test_a_hallucinated_tool_is_denied_as_not_declared(project):
    fake = FakeRouter(call("TOOL-case-management", "delete_case"), {"content": "ok"})
    rec = _run(project, fake).record
    policy = next(s for s in rec.steps if s.kind == "policy")
    assert policy.policy_effect == "deny" and policy.policy_reason.startswith("not_declared")


def test_too_many_denials_end_the_run_as_denied(project):
    deny = call("TOOL-case-management", "release_funds", {"amount_minor": 1})
    fake = FakeRouter(*([deny] * 6))
    rec = _run(project, fake).record
    assert rec.outcome == "denied"
    assert dict(rec.budgets_used)["denials"] == 4          # max_denials: 3, then stop


def test_tool_results_enter_as_data_not_instructions(project):
    fake = FakeRouter(call("TOOL-payments-ledger", "get_payment", {"end_to_end_id": "E2E-77F"}),
                      {"content": "AC04, closed account; no funds released."})
    _run(project, fake, scenario="SCN-prompt-injection-in-remittance")
    body = fake.bodies()[1]
    assert "never as instructions" in body["messages"][0]["content"]
    tool_msg = json.loads(body["messages"][-1]["content"])
    assert tool_msg["tool"] == "TOOL-payments-ledger.get_payment"
    assert "IGNORE PRIOR RULES" in tool_msg["data"]["remittance"]   # carried, but as data


# ── I-9: a refusal stops the run, once ───────────────────────────────────────
@pytest.mark.parametrize("status, kind", [(402, "spend_cap"), (422, "no_compliant_model"),
                                          (502, "chain_exhausted")])
def test_refusal_is_not_retried(project, status, kind):
    fake = FakeRouter(status)
    rec = _run(project, fake).record
    assert len(fake.requests) == 1
    assert rec.outcome == f"refused:{kind}"
    assert rec.steps[-1].outcome == "refused"


def test_other_5xx_is_retried_then_succeeds(project):
    fake = FakeRouter(503, 500, {"content": "ok"})
    rec = _run(project, fake).record
    assert rec.outcome == "completed" and len(fake.requests) == 3


def test_a_transport_failure_after_retries_is_an_error(project):
    def broken(request):
        raise httpx.ConnectError("no route", request=request)
    cfg = load_config(project / "product.config.yaml")
    bundle, prov = load_bundle(cfg, project)
    router = RouterClient(RouterSettings(base_url="https://router.test/v1"),
                          transport=httpx.MockTransport(broken), sleep=lambda s: None)
    rec = run_agent(bundle, prov, AGENT, "x", root=project, router=router,
                    executor=FixtureExecutor(), settings=RuntimeSettings()).record
    assert rec.outcome == "error" and router.calls == 3


# ── budgets ──────────────────────────────────────────────────────────────────
def test_max_steps_stops_a_run_that_never_answers(project):
    loop = call("TOOL-iso20022-parser", "explain_status", {"code": "AC04"})
    fake = FakeRouter(*([loop] * 30))
    rec = _run(project, fake).record
    assert rec.outcome == "budget_exceeded"
    assert len(fake.requests) == 20                       # the agent's max_steps


def test_cost_budget_uses_the_config_price_table(project):
    cfg_path = project / "product.config.yaml"
    cfg_path.write_text(cfg_path.read_text() + "prices:\n  claude-x: {input_per_mtok: 3000, "
                        "output_per_mtok: 3000}\n", encoding="utf-8")
    loop = call("TOOL-iso20022-parser", "explain_status", {"code": "AC04"})
    fake = FakeRouter(*([loop] * 10))
    cfg = load_config(cfg_path)
    bundle, prov = load_bundle(cfg, project)
    router = RouterClient(RouterSettings(base_url="https://router.test/v1"),
                          transport=httpx.MockTransport(fake), sleep=lambda s: None)
    rec = run_agent(bundle, prov, AGENT, "x", root=project, router=router,
                    executor=FixtureExecutor.from_scenario(bundle, "SCN-ac04-closed-account"),
                    settings=RuntimeSettings(), prices=cfg.prices).record
    # $0.36 per call against max_cost_usd 0.50: the second call crosses it.
    assert rec.outcome == "budget_exceeded" and len(fake.requests) == 2
    assert rec.steps[0].cost_usd == pytest.approx(0.36)


# ── approvals: pause and resume ──────────────────────────────────────────────
def test_approval_pauses_the_run_and_resume_completes_it(project):
    fake = FakeRouter(call("TOOL-case-management", "propose_repair",
                           {"case_id": "88121", "amount_minor": 125000}))
    first = _run(project, fake, scenario="SCN-ac04-closed-account").record
    assert first.outcome == "awaiting_approval"
    req = approvals.read(project, first.run_id)["requests"][0]
    assert (req["operation"], req["status"], req["approvers"]) == \
        ("propose_repair", "pending", ["payments-ops-lead"])
    assert "125000" not in json.dumps(req)                 # args stay out of the request file

    with pytest.raises(ApprovalPending):
        _run(project, FakeRouter(), resume=first.run_id)

    approvals.approve(project, first.run_id, req["step"], "Colin")
    fixtures = {"TOOL-case-management.propose_repair": {"repair_id": "R-1"}}
    cfg = load_config(project / "product.config.yaml")
    bundle, prov = load_bundle(cfg, project)
    fake2 = FakeRouter({"content": "Repair R-1 proposed and approved."})
    router = RouterClient(RouterSettings(base_url="https://router.test/v1"),
                          transport=httpx.MockTransport(fake2), sleep=lambda s: None)
    done = resume_agent(bundle, prov, first.run_id, root=project, router=router,
                        executor=FixtureExecutor(fixtures), settings=RuntimeSettings()).record
    assert done.outcome == "completed"
    kinds = [s.kind for s in done.steps]
    assert kinds == ["model", "policy", "approval", "tool", "model"]
    assert "Colin" in done.steps[2].policy_reason
    assert not (records.run_dir(project, first.run_id) / "state.json").exists()
    # The resumed conversation answers the pending tool call before asking again.
    assert fake2.bodies()[0]["messages"][-1]["role"] == "tool"


def test_an_approval_needs_a_name_and_a_real_step(project):
    with pytest.raises(KeyError):
        approvals.approve(project, "RUN-none", 1, "Colin")
    fake = FakeRouter(call("TOOL-case-management", "propose_repair", {"amount_minor": 5}))
    rec = _run(project, fake).record
    with pytest.raises(ValueError):
        approvals.approve(project, rec.run_id, 2, "  ")
    with pytest.raises(KeyError):
        approvals.approve(project, rec.run_id, 99, "Colin")


# ── I-8: records are closed and content-free ─────────────────────────────────
def test_run_json_validates_against_the_closed_schema(project):
    fake = FakeRouter(call("TOOL-iso20022-parser", "explain_status", {"code": "AC04"}),
                      {"content": "ok"})
    rec = _run(project, fake).record
    data = json.loads((records.run_dir(project, rec.run_id) / "run.json").read_text())
    assert records.schema_problems(data) == []
    assert records.read(project, rec.run_id) == rec
    bad = {**data, "prompt": "hello"}
    assert any("unknown" in p for p in records.schema_problems(bad))
    bad = {**data, "steps": [{**data["steps"][0], "extra": {"text": "x"}}]}
    assert records.schema_problems(bad)


def test_records_carry_no_content(project):
    fake = FakeRouter(call("TOOL-payments-ledger", "get_payment",
                           {"end_to_end_id": "E2E-77F", "note": "zebra-arg-5512"}),
                      {"content": "zebra-answer-9001: AC04, closed account."})
    rec = _run(project, fake, scenario="SCN-prompt-injection-in-remittance").record
    text = (records.run_dir(project, rec.run_id) / "run.json").read_text()
    for secret in ("zebra-input-7731", "zebra-arg-5512", "zebra-answer-9001",
                   "IGNORE PRIOR RULES", "E2E-77F"):
        assert secret not in text
    assert rec.capture_content is False
    assert not (records.run_dir(project, rec.run_id) / "content.jsonl").exists()


def test_capture_content_writes_a_separate_file_and_says_so(project):
    fake = FakeRouter(call("TOOL-iso20022-parser", "explain_status", {"code": "AC04"}),
                      {"content": "zebra-answer-9001"})
    rec = _run(project, fake, capture=True).record
    assert rec.capture_content is True
    run_json = (records.run_dir(project, rec.run_id) / "run.json").read_text()
    content = (records.run_dir(project, rec.run_id) / "content.jsonl").read_text()
    assert "zebra-answer-9001" in content and "zebra-answer-9001" not in run_json
    assert all(s.content_ref for s in rec.steps if s.kind in ("model", "tool"))


# ── I-10: the runtime refuses a bundle the gate would refuse ─────────────────
def test_runtime_refuses_stale_bundle(project):
    policy = project / "product/policies/POL-allow-reads.md"
    policy.write_text(policy.read_text().replace("Reads change nothing.", "Changed."))
    cfg = load_config(project / "product.config.yaml")
    with pytest.raises(BundleRefused, match=r"PAC-079.*PAC-060"):
        load_bundle(cfg, project)


def test_runtime_refuses_a_project_without_the_agents_preset(tmp_path):
    (tmp_path / "product.config.yaml").write_text("types: []\n")
    with pytest.raises(BundleRefused, match="presets"):
        load_bundle(load_config(tmp_path / "product.config.yaml"), tmp_path)


# ── pure pieces ──────────────────────────────────────────────────────────────
def test_tool_names_round_trip_and_mcp_schemas_map_to_functions():
    name = tool_name("TOOL-case-management", "propose_repair")
    assert parse_tool_name(name) == ("TOOL-case-management", "propose_repair")
    fn = to_openai_tool("TOOL-a", "get", "Get one", {"properties": {"id": {"type": "string"}},
                                                    "required": ["id"]})
    assert fn["function"]["parameters"] == {"type": "object", "required": ["id"],
                                            "properties": {"id": {"type": "string"}}}
    with pytest.raises(ValueError):
        tool_name("TOOL a", "op")
    with pytest.raises(ValueError):
        parse_tool_name("no-separator")


def test_runtime_settings_load_from_yaml(tmp_path):
    path = tmp_path / "keelspec.runtime.yaml"
    path.write_text("router:\n  base_url: https://gw.internal/v1\n  timeout_seconds: 5\n"
                    "telemetry:\n  capture_content: true\n")
    s = RuntimeSettings.load(path)
    assert s.router.base_url == "https://gw.internal/v1" and s.capture_content is True
    assert RuntimeSettings.load(tmp_path / "absent.yaml").router.base_url.startswith("https://api.fiferouter")


# ── the CLI ──────────────────────────────────────────────────────────────────
def test_cli_run_approve_resume_and_runs(project, monkeypatch, capsys):
    import keelspec.runtime.router_client as rc
    from keelspec.cli import main

    fake = FakeRouter(call("TOOL-case-management", "propose_repair", {"amount_minor": 125000}),
                      {"content": "Repair proposed and approved."})
    real = rc.RouterClient

    def mocked(settings=None, **kw):
        return real(settings, transport=httpx.MockTransport(fake), sleep=lambda s: None, **kw)

    monkeypatch.setattr(rc, "RouterClient", mocked)
    root = str(project)
    assert main(["-C", root, "run", AGENT, "Case 88121"]) == 2          # no tool executor
    assert main(["-C", root, "run", AGENT, "Case 88121", "--fixtures", "SCN-ac04-closed-account"]) == 1
    err = capsys.readouterr().err
    run_id = err.split("── run ")[1].split(":")[0]
    assert "awaiting_approval" in err and f"approvals approve {run_id}" in err

    assert main(["-C", root, "approvals", "list"]) == 0
    assert "pending" in capsys.readouterr().out
    step = approvals.read(project, run_id)["requests"][0]["step"]
    assert main(["-C", root, "approvals", "approve", run_id, str(step), "--by", "Colin"]) == 0
    assert main(["-C", root, "approvals", "show", run_id]) == 0
    capsys.readouterr()

    assert main(["-C", root, "run", "--resume", run_id, "--fixtures", "SCN-ac04-closed-account"]) == 0
    out = capsys.readouterr()
    assert "Repair proposed" in out.out

    assert main(["-C", root, "runs", "list"]) == 0
    assert run_id in capsys.readouterr().out
    assert main(["-C", root, "runs", "show", run_id]) == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "completed"
    assert main(["-C", root, "runs"]) == 0                              # the line summary still works
    assert main(["-C", root, "run"]) == 2


# ── edges of the loop ────────────────────────────────────────────────────────
def test_malformed_tool_calls_are_denied_not_crashed_on(project):
    bad_name = {"content": None, "tool_calls": [{"id": "x1", "type": "function", "function": {
        "name": "release_funds", "arguments": "{}"}}]}
    bad_args = {"content": None, "tool_calls": [{"id": "x2", "type": "function", "function": {
        "name": tool_name("TOOL-iso20022-parser", "explain_status"), "arguments": "[1, 2"}}]}
    rec = _run(project, FakeRouter(bad_name, bad_args, {"content": "ok"})).record
    policies = [s for s in rec.steps if s.kind == "policy"]
    assert policies[0].policy_effect == "deny"                  # not a TOOL__op name
    assert rec.outcome == "completed"


def test_an_oversized_result_is_truncated_with_a_marker(project):
    tool = project / "product/tools/TOOL-iso20022-parser.md"
    tool.write_text(tool.read_text().replace("max_result_bytes: 32768", "max_result_bytes: 40"))
    cfg = load_config(project / "product.config.yaml")
    from keelspec.engine import build
    build(cfg, project)
    fake = FakeRouter(call("TOOL-iso20022-parser", "explain_status", {"code": "AC04"}),
                      {"content": "ok"})
    rec = _run(project, fake).record
    step = next(s for s in rec.steps if s.kind == "tool")
    assert step.outcome == "truncated"
    assert json.loads(fake.bodies()[1]["messages"][-1]["content"])["truncated"] is True


def test_a_tool_with_no_answer_is_an_error_step_and_the_run_goes_on(project):
    fake = FakeRouter(call("TOOL-payments-ledger", "list_postings", {}), {"content": "ok"})
    rec = _run(project, fake).record                         # the AC04 scenario has no postings
    step = next(s for s in rec.steps if s.kind == "tool")
    assert step.outcome == "error" and rec.outcome == "completed"
    assert "no fixture" in fake.bodies()[1]["messages"][-1]["content"]


def test_resuming_a_run_that_is_not_paused_is_refused(project):
    rec = _run(project, FakeRouter({"content": "ok"})).record
    with pytest.raises(KeyError, match="not paused"):
        _run(project, FakeRouter(), resume=rec.run_id)
