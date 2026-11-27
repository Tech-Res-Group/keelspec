# Observability: traces and metrics from governed agents

`keelspec run` and `keelspec simulate` emit OpenTelemetry traces and metrics when you
point them at an OTLP endpoint. Without that, telemetry is a no-op and nothing
changes.

```bash
pip install 'keelspec[otel]'
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
keelspec run AGENT-payment-exceptions "Case 88121: pacs.002 RJCT AC04 on E2E-77F"
```

## What you get

One run is one trace:

```
keelspec.run                   keelspec.agent.id, keelspec.run.id, keelspec.bundle.sha256,
│                              keelspec.outcome, keelspec.simulated
├── keelspec.step 1
│   └── chat auto              gen_ai.operation.name=chat, gen_ai.request.model=auto,
│                              gen_ai.response.model (the model the router served),
│                              gen_ai.usage.input_tokens / output_tokens,
│                              keelspec.router.concept / rung / attempts
├── keelspec.step 2
│   ├── keelspec.policy        keelspec.policy.effect / ids / reason
│   └── execute_tool TOOL-x.op gen_ai.operation.name=execute_tool, gen_ai.tool.name,
│                              keelspec.tool.id / side_effects / outcome / truncated
└── keelspec.approval          when the run pauses for a person
```

A denied call has a policy span and no `execute_tool` span: it never ran. A run that
pauses for approval and is resumed later stays in the same trace; the resumed part
is a second `keelspec.run` span with `keelspec.resumed=true`. `keelspec simulate`
tags its spans and metrics `keelspec.simulated=true`, so CI replays do not mix with
production runs.

Metrics: `keelspec.runs` (by agent and outcome), `keelspec.policy.decisions` (by
effect and policy id), `keelspec.run.duration`, `keelspec.run.cost_usd`, and
`gen_ai.client.token.usage`.

Model and tool spans follow the OpenTelemetry GenAI semantic conventions. Those
conventions are still marked as in development; KeelSpec pins the names it uses in
one module, `keelspec/runtime/telemetry.py`.

The router call carries a W3C `traceparent` from its `chat` span, and HTTP MCP
servers receive the run's. Router-side and tool-side logs can be joined to the
trace by trace id.

## No content by default

Spans carry ids, counts, effects and outcomes. They do not carry prompts,
completions, tool arguments or tool results, so the trace is safe to send to a
shared backend or a SIEM. To include content, for debugging in a private
environment, set `telemetry.capture_content: true` in `keelspec.runtime.yaml` or run
with `--capture-content`. That switch also writes `content.jsonl` next to the run
record, and the record says capture was on. Approvers appear as roles, never as
people's names.

## Configuration

Everything comes from the standard OpenTelemetry environment variables; KeelSpec
adds none of its own.

| Variable | Effect |
|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` (or `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`) | Turns export on. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` (default) or `grpc`. |
| `OTEL_EXPORTER_OTLP_HEADERS` | Auth headers, e.g. `Authorization=Basic ...`. |
| `OTEL_SERVICE_NAME` | Defaults to `keelspec`. |
| `OTEL_METRICS_EXPORTER=none` | Traces only (for backends that take no metrics). |
| `OTEL_SDK_DISABLED=true` | Off. |

Keep keys in the environment or your secret store, never in
`keelspec.runtime.yaml` or the repository.

## Recipe: Langfuse

Langfuse accepts OTLP traces over HTTP and reads the `gen_ai.*` attributes. It does
not take metrics.

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://cloud.langfuse.com/api/public/otel"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic $(printf '%s:%s' "$LANGFUSE_PUBLIC_KEY" "$LANGFUSE_SECRET_KEY" | base64)"
export OTEL_METRICS_EXPORTER=none
keelspec run AGENT-payment-exceptions "Case 88121: pacs.002 RJCT AC04 on E2E-77F"
```

Use your region's host (the US region is `us.cloud.langfuse.com`), or your own
host if you self-host Langfuse. Check Langfuse's OpenTelemetry documentation for the
current endpoint.

## Recipe: Grafana Tempo (local)

The `grafana/otel-lgtm` image bundles an OpenTelemetry collector, Tempo for traces,
a Prometheus-compatible store for metrics, and Grafana, which is enough to look at
runs on a laptop:

```bash
docker run --rm -p 3000:3000 -p 4317:4317 -p 4318:4318 grafana/otel-lgtm
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
keelspec simulate
```

Open Grafana on `http://localhost:3000`, go to Explore, pick the Tempo data source,
and search for `service.name = keelspec`. Metrics such as `keelspec_runs_total` are
in the Prometheus data source. In a shared Tempo deployment without a metrics
backend, set `OTEL_METRICS_EXPORTER=none`.
