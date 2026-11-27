"""OpenTelemetry for the governed-agent runtime (spec section 8, M10).

One run is one trace::

    keelspec.run                   agent, run id, bundle sha, outcome
    ├── keelspec.step 1
    │   └── chat {model}           gen_ai.* request/response/usage, keelspec.router.*
    ├── keelspec.step 2
    │   ├── keelspec.policy        effect, policy ids, reason
    │   └── execute_tool {name}    gen_ai.tool.*, keelspec.tool.*
    └── keelspec.approval          when the run pauses for a person

Model and tool spans follow the OpenTelemetry GenAI semantic conventions; anything
KeelSpec-specific lives under ``keelspec.``. **Every attribute and metric name is in
this module**, so a convention change is a one-file edit. The names are pinned
against ``opentelemetry-semantic-conventions`` 0.66b2 (the GenAI conventions are
still in development upstream).

Content (messages, tool arguments and results) is set only when
``capture_content`` is on (I-8); with it off, spans carry ids, counts, effects and
outcomes, never what was said.

The API is optional. Without ``opentelemetry`` installed every span is a no-op and
the runtime behaves identically. With only the API installed (no SDK configured),
spans are non-recording and the run falls back to its own ``traceparent``.
``configure_from_env`` installs an OTLP exporter from the standard ``OTEL_*``
variables (``pip install 'keelspec[otel]'``).
"""
from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import sys
from collections.abc import Callable, Iterator, Mapping
from typing import Any

# ── names (pinned; see the module docstring) ─────────────────────────────────
SEMCONV_PINNED = "opentelemetry-semantic-conventions 0.66b2"

GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_CONVERSATION_ID = "gen_ai.conversation.id"
GEN_AI_AGENT_ID = "gen_ai.agent.id"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_INPUT_MESSAGES = "gen_ai.input.messages"
GEN_AI_OUTPUT_MESSAGES = "gen_ai.output.messages"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_TOOL_TYPE = "gen_ai.tool.type"
GEN_AI_TOOL_CALL_ID = "gen_ai.tool.call.id"
GEN_AI_TOOL_CALL_ARGUMENTS = "gen_ai.tool.call.arguments"
GEN_AI_TOOL_CALL_RESULT = "gen_ai.tool.call.result"
GEN_AI_TOKEN_TYPE = "gen_ai.token.type"

OP_CHAT = "chat"
OP_EXECUTE_TOOL = "execute_tool"
OP_INVOKE_AGENT = "invoke_agent"

KS_AGENT_ID = "keelspec.agent.id"
KS_RUN_ID = "keelspec.run.id"
KS_BUNDLE_SHA = "keelspec.bundle.sha256"
KS_OUTCOME = "keelspec.outcome"
KS_SIMULATED = "keelspec.simulated"
KS_RESUMED = "keelspec.resumed"
KS_STEP = "keelspec.step"
KS_ROUTER_CONCEPT = "keelspec.router.concept"
KS_ROUTER_RUNG = "keelspec.router.rung"
KS_ROUTER_ATTEMPTS = "keelspec.router.attempts"
KS_POLICY_EFFECT = "keelspec.policy.effect"
KS_POLICY_IDS = "keelspec.policy.ids"
KS_POLICY_ID = "keelspec.policy.id"
KS_POLICY_REASON = "keelspec.policy.reason"
KS_TOOL_ID = "keelspec.tool.id"
KS_TOOL_OPERATION = "keelspec.tool.operation"
KS_TOOL_SIDE_EFFECTS = "keelspec.tool.side_effects"
KS_TOOL_TRUNCATED = "keelspec.tool.truncated"
KS_TOOL_OUTCOME = "keelspec.tool.outcome"
KS_APPROVERS = "keelspec.approval.approvers"

SPAN_RUN = "keelspec.run"
SPAN_POLICY = "keelspec.policy"
SPAN_APPROVAL = "keelspec.approval"

M_RUNS = "keelspec.runs"
M_POLICY_DECISIONS = "keelspec.policy.decisions"
M_RUN_DURATION = "keelspec.run.duration"
M_RUN_COST = "keelspec.run.cost_usd"
M_TOKEN_USAGE = "gen_ai.client.token.usage"

CONTENT_KEYS = frozenset({GEN_AI_INPUT_MESSAGES, GEN_AI_OUTPUT_MESSAGES,
                          GEN_AI_TOOL_CALL_ARGUMENTS, GEN_AI_TOOL_CALL_RESULT})


class _NoSpan:
    """Stands in for a span when OpenTelemetry is not installed."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, *args: Any, **kw: Any) -> None:
        pass


def _clean(attrs: Mapping[str, Any]) -> dict[str, Any]:
    """OTel attribute values must be primitives or sequences of one primitive type."""
    out: dict[str, Any] = {}
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, (tuple, list)):
            out[key] = [str(v) for v in value]
        elif isinstance(value, (str, bool, int, float)):
            out[key] = value
        else:
            out[key] = str(value)
    return out


class Telemetry:
    """Span and metric helpers for one process. Cheap to construct; the default uses
    the global tracer and meter providers."""

    def __init__(self, capture_content: bool = False, simulated: bool = False,
                 tracer_provider: Any = None, meter_provider: Any = None):
        self.capture_content = capture_content
        self.simulated = simulated
        try:
            from opentelemetry import metrics, trace
        except ImportError:
            self._trace = None
            return
        from .. import __version__
        self._trace = trace
        self.tracer = (tracer_provider or trace.get_tracer_provider()).get_tracer(
            "keelspec", __version__)
        meter = (meter_provider or metrics.get_meter_provider()).get_meter("keelspec", __version__)
        self._runs = meter.create_counter(M_RUNS, unit="{run}", description="governed agent runs")
        self._decisions = meter.create_counter(M_POLICY_DECISIONS, unit="{decision}",
                                               description="policy decisions on tool calls")
        self._duration = meter.create_histogram(M_RUN_DURATION, unit="s",
                                                description="wall-clock time of a run")
        self._cost = meter.create_histogram(M_RUN_COST, unit="USD", description="cost of a run")
        self._tokens = meter.create_histogram(M_TOKEN_USAGE, unit="{token}",
                                              description="tokens used per model call")

    @property
    def enabled(self) -> bool:
        return self._trace is not None

    # ── spans ────────────────────────────────────────────────────────────────
    @contextlib.contextmanager
    def span(self, name: str, attrs: Mapping[str, Any] | None = None, *, client: bool = False,
             parent_traceparent: str | None = None) -> Iterator[Any]:
        if self._trace is None:
            yield _NoSpan()
            return
        context = None
        if parent_traceparent:
            from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
            context = TraceContextTextMapPropagator().extract({"traceparent": parent_traceparent})
        kind = self._trace.SpanKind.CLIENT if client else self._trace.SpanKind.INTERNAL
        clean = _clean(attrs or {})
        if not self.capture_content:
            clean = {k: v for k, v in clean.items() if k not in CONTENT_KEYS}
        with self.tracer.start_as_current_span(name, context=context, kind=kind,
                                               attributes=clean) as span:
            yield span

    def set(self, span: Any, attrs: Mapping[str, Any]) -> None:
        for key, value in _clean(attrs).items():
            if key in CONTENT_KEYS and not self.capture_content:
                continue
            span.set_attribute(key, value)

    def content(self, span: Any, key: str, value: Any) -> None:
        """Set a content attribute, only when capture is on (I-8)."""
        if self.capture_content:
            span.set_attribute(key, value if isinstance(value, str)
                               else json.dumps(value, default=str))

    def error(self, span: Any, description: str) -> None:
        if self._trace is not None:
            from opentelemetry.trace import Status, StatusCode
            span.set_status(Status(StatusCode.ERROR, description))

    def traceparent(self, span: Any) -> str | None:
        """The W3C traceparent of a recording span, or None (no SDK, no-op span)."""
        if self._trace is None:
            return None
        ctx = span.get_span_context()
        if not ctx.is_valid:
            return None
        return f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-{int(ctx.trace_flags):02x}"

    # ── metrics ──────────────────────────────────────────────────────────────
    def record_run(self, agent_id: str, outcome: str, seconds: float, cost_usd: float) -> None:
        if self._trace is None:
            return
        attrs = {KS_AGENT_ID: agent_id, KS_OUTCOME: outcome, KS_SIMULATED: self.simulated}
        self._runs.add(1, attrs)
        self._duration.record(seconds, attrs)
        self._cost.record(cost_usd, attrs)

    def record_decision(self, agent_id: str, effect: str, policy_ids: tuple[str, ...]) -> None:
        if self._trace is None:
            return
        for pid in policy_ids or ("none",):
            self._decisions.add(1, {KS_AGENT_ID: agent_id, KS_POLICY_EFFECT: effect,
                                    KS_POLICY_ID: pid, KS_SIMULATED: self.simulated})

    def record_tokens(self, model: str | None, input_tokens: int | None,
                      output_tokens: int | None) -> None:
        if self._trace is None:
            return
        for kind, n in (("input", input_tokens), ("output", output_tokens)):
            if n is not None:
                self._tokens.record(n, {GEN_AI_OPERATION_NAME: OP_CHAT, GEN_AI_TOKEN_TYPE: kind,
                                        GEN_AI_RESPONSE_MODEL: model or "unknown"})


# ── exporter setup from the standard environment ─────────────────────────────
@dataclasses.dataclass
class Configured:
    tracer_provider: Any
    meter_provider: Any
    shutdown: Callable[[], None]


def _exporters(protocol: str):
    if protocol == "grpc":
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    else:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    return OTLPSpanExporter, OTLPMetricExporter


def configure_from_env(env: Mapping[str, str] | None = None, install: bool = True,
                       warn=lambda msg: print(msg, file=sys.stderr)) -> Configured | None:
    """Export spans (and metrics) over OTLP when ``OTEL_EXPORTER_OTLP_ENDPOINT`` or
    ``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`` is set. Endpoint, headers and protocol come
    from the standard ``OTEL_*`` variables, which the exporters read themselves.
    ``OTEL_METRICS_EXPORTER=none`` turns metrics off (Langfuse and Tempo take traces
    only); ``OTEL_SDK_DISABLED=true`` turns everything off. Returns None when nothing
    was configured."""
    env = os.environ if env is None else env
    if str(env.get("OTEL_SDK_DISABLED", "")).lower() == "true":
        return None
    if not (env.get("OTEL_EXPORTER_OTLP_ENDPOINT") or env.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")):
        return None
    if str(env.get("OTEL_TRACES_EXPORTER", "otlp")).lower() == "none":
        return None
    protocol = env.get("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    try:
        from opentelemetry import metrics, trace
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        span_exporter, metric_exporter = _exporters(protocol)
    except ImportError:
        warn("OTEL_EXPORTER_OTLP_ENDPOINT is set but the exporter is not installed; "
             "telemetry is off:\n\n    pip install 'keelspec[otel]'\n")
        return None
    resource = Resource.create({"service.name": env.get("OTEL_SERVICE_NAME") or "keelspec"})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter()))
    readers = []
    if str(env.get("OTEL_METRICS_EXPORTER", "otlp")).lower() != "none":
        readers.append(PeriodicExportingMetricReader(metric_exporter()))
    meter_provider = MeterProvider(resource=resource, metric_readers=readers)
    if install:
        trace.set_tracer_provider(tracer_provider)
        metrics.set_meter_provider(meter_provider)

    def shutdown() -> None:
        tracer_provider.shutdown()
        meter_provider.shutdown()
    return Configured(tracer_provider, meter_provider, shutdown)
