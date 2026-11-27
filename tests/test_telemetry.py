"""v2 M10: OpenTelemetry spans and metrics from the runtime.

An in-memory span exporter and metric reader; a scripted router; scenario fixtures
for tools. Asserts the span tree of spec section 8, the content switch (I-8) in both
modes, and that the router receives the run's trace context.
"""
from __future__ import annotations

import io
import json
import sys

import httpx
import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from test_runtime import AGENT, SECRET_INPUT, FakeRouter, call, project  # noqa: F401

from keelspec.config import load_config
from keelspec.runtime import approvals
from keelspec.runtime import simulate as sim
from keelspec.runtime import telemetry as T
from keelspec.runtime.agent import resume_agent, run_agent
from keelspec.runtime.bundle import load_bundle
from keelspec.runtime.fixtures import FixtureExecutor
from keelspec.runtime.router_client import RouterClient, RouterSettings, RuntimeSettings


class Otel:
    def __init__(self, capture=False, simulated=False):
        self.spans = InMemorySpanExporter()
        self.tp = TracerProvider()
        self.tp.add_span_processor(SimpleSpanProcessor(self.spans))
        self.reader = InMemoryMetricReader()
        self.mp = MeterProvider(metric_readers=[self.reader])
        self.tel = T.Telemetry(capture_content=capture, simulated=simulated,
                               tracer_provider=self.tp, meter_provider=self.mp)

    def finished(self):
        return self.spans.get_finished_spans()

    def by_name(self, prefix):
        return [s for s in self.finished() if s.name.startswith(prefix)]

    def metrics(self) -> dict[str, list]:
        out: dict[str, list] = {}
        data = self.reader.get_metrics_data()
        for rm in data.resource_metrics:
            for sm in rm.scope_metrics:
                for m in sm.metrics:
                    out.setdefault(m.name, []).extend(m.data.data_points)
        return out


def _go(root, fake, otel, capture=False, resume=None, scenario="SCN-ac04-closed-account"):
    cfg = load_config(root / "product.config.yaml")
    bundle, prov = load_bundle(cfg, root)
    router = RouterClient(RouterSettings(base_url="https://router.test/v1"), api_key="k",
                          transport=httpx.MockTransport(fake), sleep=lambda s: None)
    kw = {"root": root, "router": router, "telemetry": otel.tel,
          "executor": FixtureExecutor.from_scenario(bundle, scenario),
          "settings": RuntimeSettings(capture_content=capture)}
    if resume:
        return resume_agent(bundle, prov, resume, **kw)
    return run_agent(bundle, prov, AGENT, SECRET_INPUT, **kw)


def _parent(span):
    return span.parent.span_id if span.parent else None


# ── the span tree ────────────────────────────────────────────────────────────
def test_span_tree_and_attributes(project):  # noqa: F811
    otel = Otel()
    fake = FakeRouter(call("TOOL-case-management", "get_case", {"case_id": "88121"}),
                      call("TOOL-case-management", "release_funds", {"amount_minor": 1}, "c2"),
                      {"content": "AC04: closed account."})
    result = _go(project, fake, otel)
    assert result.record.outcome == "completed"

    (run,) = otel.by_name("keelspec.run")
    assert run.parent is None
    assert run.attributes[T.KS_AGENT_ID] == AGENT
    assert run.attributes[T.KS_RUN_ID] == result.record.run_id
    assert run.attributes[T.KS_OUTCOME] == "completed"
    assert run.attributes[T.GEN_AI_OPERATION_NAME] == "invoke_agent"
    assert len(run.attributes[T.KS_BUNDLE_SHA]) == 64
    assert run.attributes[T.KS_SIMULATED] is False

    steps = otel.by_name("keelspec.step ")
    assert all(_parent(s) == run.context.span_id for s in steps)
    # Record steps: 1 model, 2 policy + 3 tool, 4 model, 5 policy (deny), 6 model.
    assert [s.name for s in steps] == [f"keelspec.step {n}" for n in (1, 2, 4, 5, 6)]

    chats = otel.by_name("chat ")
    assert [c.name for c in chats] == ["chat auto"] * 3
    chat = chats[0]
    assert _parent(chat) == steps[0].context.span_id
    assert chat.kind.name == "CLIENT"
    a = chat.attributes
    assert a[T.GEN_AI_OPERATION_NAME] == "chat" and a[T.GEN_AI_REQUEST_MODEL] == "auto"
    assert a[T.GEN_AI_RESPONSE_MODEL] == "claude-x"
    assert a[T.GEN_AI_USAGE_INPUT_TOKENS] == 100 and a[T.GEN_AI_USAGE_OUTPUT_TOKENS] == 20
    assert a[T.KS_ROUTER_CONCEPT] == "moneypath.verify"
    assert a[T.KS_ROUTER_RUNG] == "1" and a[T.KS_ROUTER_ATTEMPTS] == 1
    assert a[T.GEN_AI_CONVERSATION_ID] == result.record.run_id

    policies = otel.by_name("keelspec.policy")
    assert [(p.attributes[T.KS_TOOL_OPERATION], p.attributes[T.KS_POLICY_EFFECT],
             tuple(p.attributes[T.KS_POLICY_IDS])) for p in policies] == [
        ("get_case", "redact", ("POL-allow-reads", "POL-pii-redaction")),
        ("release_funds", "deny", ("POL-no-funds-movement",))]
    assert _parent(policies[0]) == steps[1].context.span_id

    (tool,) = otel.by_name("execute_tool ")            # the denied call never executes
    assert tool.name == "execute_tool TOOL-case-management.get_case"
    assert _parent(tool) == steps[1].context.span_id
    t = tool.attributes
    assert t[T.GEN_AI_OPERATION_NAME] == "execute_tool" and t[T.GEN_AI_TOOL_CALL_ID] == "c1"
    assert t[T.KS_TOOL_SIDE_EFFECTS] == "read" and t[T.KS_TOOL_OUTCOME] == "ok"
    assert t[T.KS_TOOL_TRUNCATED] is False
    assert {s.context.trace_id for s in otel.finished()} == {run.context.trace_id}


def test_traceparent_reaches_the_router_from_the_chat_span(project):  # noqa: F811
    otel = Otel()
    fake = FakeRouter({"content": "done"})
    _go(project, fake, otel)
    (chat,) = otel.by_name("chat ")
    header = fake.requests[0].headers["traceparent"]
    _version, trace_id, span_id, _flags = header.split("-")
    assert int(trace_id, 16) == chat.context.trace_id
    assert int(span_id, 16) == chat.context.span_id


def test_approval_pause_and_resume_stay_in_one_trace(project):  # noqa: F811
    otel = Otel()
    fake = FakeRouter(call("TOOL-case-management", "propose_repair", {"amount_minor": 125000}),
                      {"content": "Repair proposed."})
    paused = _go(project, fake, otel)
    assert paused.record.outcome == "awaiting_approval"
    (approval,) = otel.by_name("keelspec.approval")
    assert approval.attributes[T.KS_OUTCOME] == "awaiting_approval"
    assert list(approval.attributes[T.KS_APPROVERS]) == ["payments-ops-lead"]

    run_id = paused.record.run_id
    step = approvals.read(project, run_id)["requests"][0]["step"]
    approvals.approve(project, run_id, step, "Colin")
    done = _go(project, fake, otel, resume=run_id)
    assert done.record.outcome == "completed"
    runs = otel.by_name("keelspec.run")
    assert len(runs) == 2 and runs[1].attributes[T.KS_RESUMED] is True
    assert runs[0].context.trace_id == runs[1].context.trace_id
    approved = [s for s in otel.by_name("keelspec.approval")
                if s.attributes[T.KS_OUTCOME] == "approved"]
    assert len(approved) == 1
    # No person's name in telemetry: approvers are roles.
    assert "Colin" not in json.dumps([dict(s.attributes) for s in otel.finished()])


def test_refusal_marks_spans_as_errors(project):  # noqa: F811
    otel = Otel()
    _go(project, FakeRouter(402), otel)
    (run,) = otel.by_name("keelspec.run")
    (chat,) = otel.by_name("chat ")
    assert run.attributes[T.KS_OUTCOME] == "refused:spend_cap"
    assert run.status.status_code.name == "ERROR" and chat.status.status_code.name == "ERROR"


# ── I-8: content only with capture on ────────────────────────────────────────
def _span_text(otel) -> str:
    return json.dumps([{"name": s.name, **dict(s.attributes)} for s in otel.finished()],
                      default=str)


def test_spans_carry_no_content_with_capture_off(project):  # noqa: F811
    otel = Otel(capture=False)
    fake = FakeRouter(call("TOOL-payments-ledger", "get_payment",
                           {"end_to_end_id": "E2E-77F", "note": "zebra-arg-5512"}),
                      {"content": "final answer zebra-answer-9001"})
    _go(project, fake, otel)
    text = _span_text(otel)
    for secret in ("zebra-input-7731", "zebra-arg-5512", "zebra-answer-9001", "INV-2231",
                   "You are investigating"):
        assert secret not in text, secret
    assert not any(k in text for k in T.CONTENT_KEYS)


def test_spans_carry_content_with_capture_on(project):  # noqa: F811
    otel = Otel(capture=True)
    fake = FakeRouter(call("TOOL-payments-ledger", "get_payment",
                           {"end_to_end_id": "E2E-77F", "note": "zebra-arg-5512"}),
                      {"content": "final answer zebra-answer-9001"})
    _go(project, fake, otel, capture=True)
    chat = otel.by_name("chat ")[0].attributes
    assert "zebra-input-7731" in chat[T.GEN_AI_INPUT_MESSAGES]
    assert T.GEN_AI_OUTPUT_MESSAGES in chat
    tool = otel.by_name("execute_tool ")[0].attributes
    assert "zebra-arg-5512" in tool[T.GEN_AI_TOOL_CALL_ARGUMENTS]
    assert "INV-2231" in tool[T.GEN_AI_TOOL_CALL_RESULT]
    assert "zebra-answer-9001" in otel.by_name("chat ")[1].attributes[T.GEN_AI_OUTPUT_MESSAGES]


def test_content_keys_are_dropped_from_span_attrs_when_off():
    otel = Otel(capture=False)
    with otel.tel.span("x", {T.GEN_AI_INPUT_MESSAGES: "secret", "keep": 1}) as span:
        otel.tel.set(span, {T.GEN_AI_TOOL_CALL_RESULT: "secret", "also": ("a", 2)})
        otel.tel.content(span, T.GEN_AI_OUTPUT_MESSAGES, ["secret"])
    attrs = dict(otel.finished()[0].attributes)
    assert attrs == {"keep": 1, "also": ("a", "2")}


# ── metrics ──────────────────────────────────────────────────────────────────
def test_metrics(project):  # noqa: F811
    otel = Otel()
    fake = FakeRouter(call("TOOL-case-management", "get_case", {"case_id": "88121"}),
                      call("TOOL-case-management", "release_funds", {}, "c2"),
                      {"content": "done"})
    _go(project, fake, otel)
    m = otel.metrics()
    (runs,) = m[T.M_RUNS]
    assert runs.value == 1 and runs.attributes[T.KS_OUTCOME] == "completed"
    decisions = {(p.attributes[T.KS_POLICY_EFFECT], p.attributes[T.KS_POLICY_ID]): p.value
                 for p in m[T.M_POLICY_DECISIONS]}
    assert decisions == {("redact", "POL-allow-reads"): 1, ("redact", "POL-pii-redaction"): 1,
                         ("deny", "POL-no-funds-movement"): 1}
    tokens = {p.attributes[T.GEN_AI_TOKEN_TYPE]: p.sum for p in m[T.M_TOKEN_USAGE]}
    assert tokens == {"input": 300, "output": 60}
    assert m[T.M_RUN_DURATION][0].count == 1 and m[T.M_RUN_COST][0].count == 1


def test_no_policy_decision_is_counted_as_none():
    otel = Otel()
    otel.tel.record_decision(AGENT, "deny", ())
    (p,) = otel.metrics()[T.M_POLICY_DECISIONS]
    assert p.attributes[T.KS_POLICY_ID] == "none"


# ── simulate is tagged ───────────────────────────────────────────────────────
def test_simulate_spans_are_tagged(monkeypatch):
    otel = Otel()
    monkeypatch.setattr(sim, "Telemetry", lambda simulated: T.Telemetry(
        simulated=simulated, tracer_provider=otel.tp, meter_provider=otel.mp))
    from test_simulate import INJECTION, _bundle, _scenario
    bundle, prov = _bundle()
    assert sim.run_scenario(bundle, prov, _scenario(bundle, INJECTION)).passed
    (run,) = otel.by_name("keelspec.run")
    assert run.attributes[T.KS_SIMULATED] is True
    assert all(p.attributes[T.KS_SIMULATED] for p in otel.metrics()[T.M_RUNS])


# ── without OpenTelemetry ────────────────────────────────────────────────────
def test_noop_without_opentelemetry(monkeypatch, project):  # noqa: F811
    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    tel = T.Telemetry()
    assert not tel.enabled
    with tel.span("x", {"a": 1}) as span:
        tel.set(span, {"b": 2})
        tel.content(span, T.GEN_AI_INPUT_MESSAGES, "x")
        tel.error(span, "boom")
        assert tel.traceparent(span) is None
    tel.record_run(AGENT, "completed", 1.0, 0.0)
    tel.record_decision(AGENT, "allow", ("P",))
    tel.record_tokens("m", 1, 2)

    class NoTel:
        def __init__(self):
            self.tel = tel
    fake = FakeRouter({"content": "done"})
    result = _go(project, fake, NoTel())
    assert result.record.outcome == "completed"
    assert fake.requests[0].headers["traceparent"].startswith("00-")   # still propagated


def test_api_only_spans_fall_back_to_our_traceparent():
    from opentelemetry.trace import NonRecordingSpan
    from opentelemetry.trace.span import INVALID_SPAN_CONTEXT
    assert T.Telemetry().traceparent(NonRecordingSpan(INVALID_SPAN_CONTEXT)) is None


# ── exporter configuration ───────────────────────────────────────────────────
def test_configure_from_env_does_nothing_unless_asked():
    assert T.configure_from_env({}) is None
    on = {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318"}
    assert T.configure_from_env({**on, "OTEL_SDK_DISABLED": "true"}) is None
    assert T.configure_from_env({**on, "OTEL_TRACES_EXPORTER": "none"}) is None


def test_configure_from_env_warns_without_the_exporter(monkeypatch):
    def missing(protocol):
        raise ImportError("no exporter")
    monkeypatch.setattr(T, "_exporters", missing)
    said = []
    assert T.configure_from_env({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://x"},
                                warn=said.append) is None
    assert "keelspec[otel]" in said[0]


def test_configure_from_env_builds_providers(monkeypatch):
    spans = InMemorySpanExporter()
    seen = {}

    def exporters(protocol):
        seen["protocol"] = protocol
        return (lambda: spans), (lambda: ConsoleMetricExporter(out=io.StringIO()))
    monkeypatch.setattr(T, "_exporters", exporters)
    env = {"OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://x", "OTEL_SERVICE_NAME": "payments",
           "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc"}
    configured = T.configure_from_env(env, install=False)
    assert seen["protocol"] == "grpc"
    assert configured.tracer_provider.resource.attributes["service.name"] == "payments"
    tel = T.Telemetry(tracer_provider=configured.tracer_provider,
                      meter_provider=configured.meter_provider)
    with tel.span("hello"):
        pass
    configured.shutdown()
    assert [s.name for s in spans.get_finished_spans()] == ["hello"]
    quiet = T.configure_from_env({**env, "OTEL_METRICS_EXPORTER": "none"}, install=False)
    assert quiet is not None
    quiet.shutdown()


def test_cli_flushes_telemetry(monkeypatch, project, capsys):  # noqa: F811
    from keelspec.cli import main
    flushed = []
    monkeypatch.setattr(T, "configure_from_env",
                        lambda: T.Configured(None, None, lambda: flushed.append(True)))
    assert main(["-C", str(project), "simulate", "SCN-ac04-closed-account"]) == 0
    assert flushed == [True]
