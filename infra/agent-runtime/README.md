# infra/agent-runtime: running `keelspec serve` in a container

A recipe for hosting governed agents over HTTP. It is separate from the Terraform
stack in `infra/`, which runs keelspec.com: nothing here creates cloud resources,
and nothing here has been deployed.

## What the container does

- Serves the agents in one product repository: `POST /v1/agents/{id}/runs`,
  `GET /v1/runs/{id}`, `POST /v1/runs/{id}/approvals`, `GET /healthz`.
- Executes the committed bundle and refuses to start if it fails validation. The
  image build runs `keelspec validate` too, so a failing bundle never becomes an
  image.
- Serves only agents with `status: deployed`.
- Reaches the model at the endpoint set in `keelspec.runtime.yaml` (hosted
  FifeRouter, a self-hosted router, or any OpenAI-compatible endpoint) and tools
  through MCP, exactly as `keelspec run` does. There is no default: without
  `router.base_url` the server refuses to start.

## Build

From the root of your product repository (where `product.config.yaml` is), with a
`.dockerignore` that keeps local state and secrets out of the image:

```
.git
.keelspec
.venv
**/__pycache__
.env
*.tfvars
```

```bash
docker build -f <path-to-keelspec>/infra/agent-runtime/Dockerfile \
  --build-arg KEELSPEC_SPEC="keelspec[runtime,otel]==<version>" \
  -t payments-agents .
```

## Run

Secrets come from the environment at run time, never from the image or the
repository:

| Variable | Purpose |
|---|---|
| `KEELSPEC_SERVE_TOKEN` | Required. Bearer token for starting runs and reading records. |
| `KEELSPEC_APPROVER_TOKEN` | Optional, and must differ. The only token that can approve a paused call. Without it, approvals over HTTP are off and a person signs with `keelspec approvals approve`. |
| `FIFEROUTER_API_KEY` | The router key (or whatever `router.api_key_env` names). |
| `OTEL_EXPORTER_OTLP_ENDPOINT` and friends | Optional traces and metrics; see `docs/observability.md`. |

```bash
docker run -d --name payments-agents -p 127.0.0.1:8080:8080 \
  -v payments-agents-state:/srv/product/.keelspec \
  -e KEELSPEC_SERVE_TOKEN -e KEELSPEC_APPROVER_TOKEN -e FIFEROUTER_API_KEY \
  payments-agents
curl -s http://127.0.0.1:8080/healthz
```

The volume matters: run records, approval requests and the state a paused run
resumes from live in `.keelspec/`. Without a volume, replacing the container loses
every run waiting for approval.

Give the two tokens to different people or systems. The point of the split is that
whoever asks an agent to act cannot approve the money-moving step it asks for.

## Hosting

**On a server you run** (for example the Hetzner box the `infra/` stack creates,
which boots with Docker): run the container bound to `127.0.0.1` as above and put
it behind the TLS reverse proxy you already use. Do not publish port 8080 to the
internet directly; the server speaks plain HTTP.

**On DigitalOcean App Platform:** create an app from the image (or from the
repository with this Dockerfile), set the HTTP port to 8080 and the health check
path to `/healthz`, and add the variables above as encrypted environment
variables. App Platform terminates TLS for you. It has no persistent disk, though,
so paused runs do not survive a redeploy; if your agents pause for approval, use a
Droplet with a block-storage volume mounted at `/srv/product/.keelspec` instead.

## Not here yet

Durable storage for run records beyond a volume, horizontal scaling (two replicas
would not share approval state), and an authenticated approval UI. Each of those
is a decision, not an oversight.
