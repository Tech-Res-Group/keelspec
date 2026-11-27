# Changelog

All notable changes to KeelSpec, published as `fastpdlc` up to and including
0.6.3. Entries below 0.7.0 use the old name; a changelog is a record, not a
description of the present. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows
[semantic versioning](https://semver.org/).

**Diagnostic codes are API.** A `PAC-NNN` is never renumbered — a check that changes
meaning gets a new code and the old one is retired. Changing the JSON bundle shape, a
config key, or the plugin `Registry` surface is a breaking change and bumps the major.

## [Unreleased]

> **Config schema.** `presets` and list-valued `references[].to` are new config keys.
> They are additive (an existing config validates unchanged), but the policy above
> treats a config-schema change as major. The version number is open decision D-1 in
> the v2 spec.

Accountability on the agent-built line, prompted by a business-stakeholder review
that asked who approves, why a change got the light path, and what a repeated failure
actually means.

### Added

- **Governed agents, M12: `keelspec serve`.** An HTTP API for deployed agents,
  standard library only: `POST /v1/agents/{id}/runs`, `GET /v1/runs/{id}` (the
  content-free record and pending approvals), `POST /v1/runs/{id}/approvals`
  (approve and resume), and `GET /healthz` (bundle sha256 and validate status). It
  executes the bundle it loaded, refuses to start on one that fails validation,
  serves only `status: deployed` agents unless `--any-status`, and opens every tool
  before a run so a drifted server refuses it (PAC-073). Two tokens, kept apart:
  `KEELSPEC_SERVE_TOKEN` starts runs and is required beyond loopback;
  `KEELSPEC_APPROVER_TOKEN`, which must differ, is the only way to approve over
  HTTP, so whoever asks an agent to act cannot approve what it asks for. Bodies are
  capped at 64 KB, errors never leak a traceback, and the request log carries
  method, path and status only. `--mcp` serves each deployed agent as one MCP tool
  on stdio. `infra/agent-runtime/` has a Dockerfile (validates at build, runs as a
  non-root user, health-checks `/healthz`) and a hosting recipe for your own server
  or DigitalOcean App Platform.
- **Governed agents, M11: agent-aware orchestration.** `keelspec orchestrate AGENT-x`
  adds two things to the line. ST-04c Tools, a machine station after Develop, finds
  the MCP servers the agent's tools need that do not exist and scaffolds them (only
  with `--write`, never on a dry run), and lists scenario fixtures that are missing;
  it does not invent fixture data, since a scenario is product intent. Verify gains
  a sixth lens, `policy`, which is code rather than a model: it searches boundary
  argument values from every `when` condition for a way to run a guarded or money
  operation with no person in the loop, plants an instruction to call each such
  operation in tool data and replays the agent with the naive scripted model, and
  replays the agent's scenarios. Its verdict joins the same refute, triage and
  repair logic as the other lenses, a risk tier's lens list never drops it, and a
  check that cannot run refutes rather than abstains. Station ids are unchanged;
  ST-04c is inserted, as ST-04b and ST-06b were.
- **Governed agents, M10: OpenTelemetry.** `keelspec run` and `keelspec simulate`
  emit one trace per run (`keelspec.run` > `keelspec.step N` > `chat` /
  `keelspec.policy` / `execute_tool`, plus `keelspec.approval`) and the metrics
  `keelspec.runs`, `keelspec.policy.decisions`, `keelspec.run.duration`,
  `keelspec.run.cost_usd` and `gen_ai.client.token.usage`. Model and tool spans
  follow the GenAI semantic conventions, with every name pinned in
  `keelspec/runtime/telemetry.py`. Spans carry no content unless capture is on (the
  same switch as `content.jsonl`); approvers appear as roles, never names. The
  router receives the `chat` span's `traceparent`, a resumed run stays in the paused
  run's trace, and simulated runs are tagged `keelspec.simulated=true`. Export is
  configured only by the standard `OTEL_*` variables (`pip install
  'keelspec[otel]'`); without OpenTelemetry the spans are no-ops. Langfuse and
  Grafana Tempo recipes are in `docs/observability.md`.
- **Governed agents, M9: simulation and evidence.** `keelspec simulate [AGENT-x|SCN-y]`
  replays scenarios offline through the real agent loop (policy engine, budgets,
  redaction, run records), with tools answering from the scenario's `fixtures` and
  the model replaced by a deterministic scripted model that is naive on purpose: it
  calls every read it can fill arguments for and obeys any instruction it finds in
  tool data. A passing scenario therefore shows the policy holding, not a model
  behaving; in the example's injection scenario it really does ask for
  `release_funds` and `POL-no-funds-movement` denies it. The `expect` keys
  (`must_call`, `must_not_call`, `call_order`, `policy_decisions`, `outcome`,
  `final_answer_contains`, `final_answer_not_contains`, `max_steps`,
  `max_cost_usd`) are deterministic checks on the run record; "called" means the tool
  ran. A `judge` block is reported and never gates. `--junit PATH` writes JUnit XML;
  `--evidence [PATH]` writes an evidence record with a `simulation` block (each
  scenario's file digest and result), and `keelspec evidence --verify` now checks
  those digests too. PAC-076: an agent marked `simulated` or `deployed` whose
  scenarios lack passing simulation evidence on their current contents is an error,
  judged only when `.keelspec/evidence` holds simulation evidence; `simulate` itself
  is not refused by PAC-076, since it produces the evidence that clears it. The
  GitHub Action takes `simulate: true` (and `junit:`) to replay scenarios in CI with
  no API key and no network.
- **Governed agents, M8: the MCP client and tool scaffolding.** `keelspec run` without
  `--fixtures` reaches each tool through MCP (stdio or streamable HTTP; one session
  per TOOL- artifact, closed when the run ends; HTTP servers receive the run's
  `traceparent`). Every session lists the server's tools and refuses to start on any
  difference from the artifact's `operations` (PAC-073), and a run opens its tools
  before the model is asked anything. `timeout_seconds` bounds every call (a
  `timeout` step) and `max_result_bytes` truncates with an explicit marker (a
  `truncated` step). `keelspec tools check [TOOL-x ...]` runs the PAC-073 comparison
  without an agent. `keelspec tools scaffold TOOL-x` generates a Python MCP server
  under `servers/<slug>/` whose tool names, docstrings and typed arguments come from
  the artifact (operations may now carry `description` and `input_schema`, which the
  model is also shown), with a test that its tool list matches the artifact. The
  example ships three reference servers built that way, backed by JSON fixtures:
  payments ledger, ISO 20022 parser (pacs.002 / pacs.008, reason codes) and case
  management, which implements `release_funds` so the policy, not the tool, is what
  stops it.
- **Governed agents, v2 milestone M5: the artifact types.** `presets: [agents]` in
  `product.config.yaml` adds four ordinary types, `agents` (AGENT-), `tools` (TOOL-),
  `policies` (POL-) and `scenarios` (SCN-), and turns on library checks inside
  `validate`: PAC-070 (a policy names an operation its tool does not declare),
  PAC-071 (an operation no linked policy permits; warning), PAC-072 (a malformed
  policy `match` or `when`), PAC-074 (a high-criticality agent can reach a money
  operation with no `require_approval` or `deny` in front of it), PAC-075 (an agent
  with no scenarios; warning) and PAC-077 (a scenario names an operation its agent
  cannot call). PAC-073, 076, 078 and 079 are registered now for the runtime
  milestones. A `redact` policy masks results and is never permission to call.
  `examples/payments-exceptions/` is the reference project: one agent, three tools,
  five policies, three scenarios, validating clean. No runtime yet.
- **Governed agents, M7: the runtime core** (`pip install 'keelspec[runtime]'`).
  `keelspec run AGENT "input"` runs one governed agent on the compiled bundle, and
  refuses (PAC-079) if `validate` reports any error or the bundle is stale. The model
  is reached through FifeRouter or any OpenAI-compatible endpoint, over HTTP only,
  with `x-fife-concept`, `x-fife-session`, `x-fife-critical` and a W3C `traceparent`
  per run; the served model, rung and attempts are recorded. The model is offered
  only the agent's declared operations, and every call passes the policy engine
  first: a denial goes back to the model as data and counts against `max_denials`;
  `require_approval` pauses the run (`keelspec approvals approve RUN STEP --by NAME`,
  then `keelspec run --resume RUN`). A 402, 422 or 502 from the router stops the run
  as `refused:<kind>` with no retry; other 5xx and transport errors are retried at
  most twice. Budgets: steps, cost (from the `prices` table), wall clock, denials.
  Run records at `.keelspec/runs/<run_id>/run.json` are a closed, content-free
  schema; `--capture-content` writes content to a separate `content.jsonl` and the
  record says so. `keelspec runs list|show` reads them; plain `keelspec runs` still
  prints the line summary. Tools answer from scenario fixtures (`--fixtures SCN-x`)
  or, from M8, from MCP servers.
- **Governed agents, M6: the policy engine.** `keelspec.runtime.policy` decides one
  tool call from the agent's linked policies: matching, `when` conditions (ANDed;
  `== != > >= < <= in not_in matches exists`, no eval), precedence
  deny > require_approval > redact > allow, and default deny (`no_policy`). Only
  `allow` and `require_approval` permit a call; `redact` masks the result. A
  condition that cannot be decided fails closed: a deny or require_approval applies,
  an allow does not. An undeclared tool or operation is never offered and is denied
  as `not_declared`. `keelspec policy explain AGENT TOOL OP '{args}'` and the MCP tools
  `product_policy_explain` and `product_agent_card` run the same code the runtime
  will, so explain and run cannot disagree. Result redaction masks fields an
  operation tags by data class (`fields: {debtor.name: pii}`, `*` for lists); an
  operation that tags nothing for a redacted class has its whole result withheld.
  Pure Python, on the core install.
- **Multi-target references**: `to: [rules, constraints, terms]` resolves a value
  against any of the listed types. LSP completion, hover and the MCP tools follow it
  with no special code. A single `to:` is unchanged.
- **Risk tiers.** `delivery` in `product.config.yaml` scores a feature's own fields
  (`risk_factors`) and picks a tier that sets its Verify lenses, required approvers,
  Clean and repair bound. The score and its reasons are recorded on the run. An
  artifact that cannot be found is assessed at the highest tier.
- **Named approvers at the human gate.** A tier's `approvers` are roles that must each
  put a name in the gate file (or `--approve ROLE=NAME`) before Design. Unlike open
  questions, a required approval cannot be made advisory.
- **ST-06b Triage**, inserted rather than renumbered. A refuted change is classified
  as requirement, design, dependency, environment, implementation, model or
  business-decision. Only implementation is repaired automatically; everything else
  ends as the new `needs-human` status with the question a person must answer.
- **A fifth Verify lens, `integrity`**: does the business process around the change
  survive it, and not just its own criteria? Every native lens now sees the
  feature's linked artifacts. The cross-provider critic deliberately does not.
- **`keelspec runs`**: status mix, first-pass and repair rates, refutations by lens,
  triage causes and risk tiers, added up from `.keelspec/runs/`. Runs are now
  timestamped.
- **`PAC-002`** (warning): a type's `recommended` field is empty.
- **Scaffold:** `outcomes` and `nfrs` types, with features linking to both, and a
  release-readiness gate in `product_hooks.py`: `PAC-903` (no outcome), `PAC-904`
  (an NFR without evidence) and `PAC-905` (no owner, rollback or runbook), all on
  `shipped`. NFR `evidence` resolves like acceptance tests.
- **[AI-GOVERNANCE.md](AI-GOVERNANCE.md)** and a scope table in the README saying what
  the line covers, and what it hands to the rest of delivery.
- **`independent_critic` on a risk tier**: the run is refused unless at least one
  critic comes from a different model vendor than the builder. When a tier does not
  require it, a same-vendor run is noted on the record instead.
- **`keelspec intake`**: a GitHub issue or Jira ticket becomes a draft feature file,
  which is then the source of truth. `--sync` shows every upstream change as a diff;
  `--apply` writes it and is refused on the default branch, so the change is merged
  through the gate. Only ticket-owned fields (title, criteria, description block)
  ever change, and a field changed on both sides stops for a person. Standard
  library only; credentials from the environment; nothing sent to a model.
- **Factory metrics, `keelspec-metrics/2`.** `keelspec runs` adds the rejection rate
  per lens (abstentions counted apart, via a new `abstained` flag on verdicts), review
  load, cost and cost per merged PR, and the spec-drift rate from kept evidence
  records (`--evidence DIR`). Every runner now records token usage per model call on
  the run (`usage`); prices come only from an optional `prices` table in
  `product.config.yaml`. A run is linked to its merge by a `KeelSpec-Run:` commit
  trailer, which `orchestrate` prints for a proposed run. Every `/1` field is unchanged.
- **Bring your own builder.** `keelspec orchestrate --builder claude-code` (or `codex`)
  runs ST-04 Develop, its repairs and ST-04b Clean through that agent's own CLI, in a
  throwaway git worktree at `HEAD`. What changed is read from git, not from the
  agent; the reviewers get the real diff. A step that touches the product directory,
  the bundle, the config, the plugin, `.keelspec/` or CI configuration is rolled back
  and fails the run. The change is saved as a patch beside the run record, and applied
  to the working tree only with `--write` and only when the line proposes it. The run
  record names the builder, its version and its base commit. KeelSpec never handles
  the agent's credentials.

### Changed

- A Develop step that fails now ends the run as `error`. It used to carry on, and
  Test and the critics would review a change that was never made.

- The Disambiguate gate file keeps every question when it is rewritten, not just
  the unresolved ones, so answers already given are no longer dropped.

- The `runtime` extra now requires `mcp>=2.0` (the client uses the 2.x `Client`
  API). The `mcp` extra for `keelspec mcp` still accepts 1.x.

### Fixed

- `keelspec mcp` works with the MCP SDK 2.x, where `FastMCP` became `MCPServer`; it
  still works with 1.x.

## [0.7.0] — 2026-09-14

### Changed

- **Renamed: FastPDLC is now KeelSpec**, and the package is `keelspec`. A keel is
  laid first and everything else is attached to it, which is what "intent first, in
  the same PR" means; a keel also resists drift, which is what `PAC-060` reports.
  The `fastpdlc` package has been removed from PyPI rather than aliased — it had no
  installs outside this author's own repositories, and an alias kept alive for nobody
  is a second name to maintain forever. The CLI is `keelspec`; the GitHub Action is
  `tarvitave/keelspec`.

  **Diagnostic codes are untouched.** `PAC-` stands for product-as-code, not for the
  product's name, so every code survives the rename — which is the behaviour the
  never-renumber rule promises.

- **Relicensed to Apache-2.0**, from LGPL-3.0-or-later. LGPL's protection assumes
  C-style linking; under pip "the user may substitute a modified version" is already
  true, so the practical obligation was near zero while the word LGPL sits on
  enterprise blocklists. Apache-2.0 also grants patents explicitly. Versions up to
  0.6.3 remain LGPL-3.0-or-later.

### Fixed

- **`__version__` was stuck at 0.4.0** while `pyproject.toml` shipped 0.6.1, 0.6.2 and
  0.6.3, so `keelspec.__version__` had been lying for three releases. Both now read
  from the same bump.

### Added

- **Concept routing per station** — `OpenAIRunner(concepts=STATION_CONCEPTS)` sends a
  different concept header for each station, where `extra_headers` alone is fixed for
  a whole run. The ROSTER's `model` column is a policy table written in Python; this
  moves that policy into the router's config. Off unless asked for, and the map is a
  plain dict because those names belong to the router operator's catalogue.


- **`keelspec validate --watch`** — the same gate, re-run whenever a `product/` file,
  the config or the committed bundle changes. Polling, so the core keeps its two
  dependencies. Not a gate: it never exits non-zero, because a red tree you are
  mid-fix should not kill the terminal you are fixing it in.

- **`keelspec lsp`** — a language server over the product graph: diagnostics,
  completion, hover, go-to-definition, find-references, workspace symbols. Needs
  `pip install 'fastpdlc[lsp]'`. A VS Code client lives in `editors/vscode/` and is
  deliberately a shim — it launches the server and owns no logic.

  Completion offers only values the validator would accept, because it reads the same
  config: the ids of the type a reference field must resolve to, or an enum's members.

  Diagnostics are `validate`'s, computed from the files **on disk** — so they refresh
  on save, not per keystroke. An editor validating the unsaved buffer would be a
  second opinion about correctness, and this project cannot have two judges.

- **`keelspec mcp`** — the same graph as six read-only tools for a coding agent:
  `product_schema`, `product_list`, `product_get`, `product_allowed_values`,
  `product_references_to`, `product_validate`. Needs `pip install 'fastpdlc[mcp]'`.
  Read-only on purpose: a server that could also write would let the thing being
  judged edit the evidence.

- **`keelspec.index`** — the resolved graph with source positions, shared by both
  surfaces so the lookups exist once. `ProductIndex`, `Artifact`, `Edge` and
  `Location` are exported from the package root.

- **The scaffold demonstrates traceability**, which is the claim worth evaluating.
  `copier copy` now produces a feature whose acceptance criterion names a test, the
  test it names, and a `product_hooks.py` that resolves the reference — so the first
  thing a new user can do is rename that test and watch the build fail with PAC-902.
  It previously scaffolded a glossary and a business rule, which demonstrated
  cross-reference checking: true, useful, and the least distinctive thing here.

  Still two types, not eight. The `rules` example is dropped rather than added to —
  the point lands faster with a glossary to point at and a feature that has to prove
  itself. `tests/test_template.py` gates the README's demo, error code included.

- `Diagnostic` gained optional `field` and `value`, naming the frontmatter key a
  finding is about and the offending value within it. `validate --json` reports them.
  Additive: `Report.add`'s existing positional signature is unchanged, so plugin
  validators keep working untouched.

### Fixed

- The reference graph is now typed at both ends. Ids are unique only *within* a type
  — which is exactly what `PAC-012` says — so a graph keyed on the bare id silently
  merged a feature with the spec sharing its name. Nothing user-visible changed in
  `validate`, which never used such an index; the new surfaces would have inherited
  the bug.

## [0.6.3] — 2026-09-02

### Fixed

- **`OpenAIRunner`/`OpenAICodingRunner` no longer send `temperature` by default.** The Claude 5
  family rejects it as a deprecated param with a 400 (`\`temperature\` is deprecated for this
  model`), which sank a gateway-routed build at station one; it also isn't needed for structured
  stations. Pass `temperature=<n>` explicitly to opt back in for a model/endpoint that still wants
  it. (Found via a live gateway build once the router surfaced the upstream reason.)

## [0.6.2] — 2026-09-02

### Fixed

- **Portable structured output across gateway-routed providers.** `OpenAIRunner` no longer sends the
  OpenAI `response_format=json_object` param by default — a gateway that routes to Anthropic returns a
  **400** on it (surfacing as `all_candidates_failed … upstream 400`). Instead it asks for a JSON
  object in the prompt and parses the reply with `extract_json_object`, which tolerates a ```json
  fence or a little surrounding prose. Opt back into strict `response_format` with `json_mode=True`
  when the endpoint supports it (e.g. OpenAI proper). The coding runner's final structured call does
  the same. `runners.extract_json_object` is public.

## [0.6.1] — 2026-09-02

### Fixed

- **Gateway failures are now diagnosable.** `openai_chat` surfaces the HTTP error *body* in the
  raised message — a bare `502 Bad Gateway` from a router is useless, whereas the body usually
  names the real cause (an upstream/BYOK failure, a too-large `max_tokens`, an unsupported param).
- **`OpenAIRunner` guards non-object JSON.** A smaller/gateway-routed model can return a bare JSON
  string or list under `json_object` mode; the runner now raises a clear error (naming the type and
  the first chars) instead of letting a `str` crash a downstream `.get()`.
- **Safer default `max_tokens` for gateway use:** `OpenAIRunner` defaults to 8192 (was 16000) and
  `OpenAICodingRunner`'s loop uses 8192/4096, since many gateway-routed models cap output well below
  16000 and reject the larger request. (The native Anthropic runners are unchanged.)

## [0.6.0] — 2026-09-02

### Added

- **OpenAI-compatible runners — the `base_url` config bridge.** `runners.OpenAIRunner` and
  `coding.OpenAICodingRunner` run the pipeline against *any* OpenAI `/chat/completions`
  endpoint — a routing gateway (e.g. Muchty), OpenRouter, a local vLLM/Ollama, or OpenAI
  itself — selected purely by `base_url`. Same `run(station, prompt, schema)` contract as
  the native Anthropic runners, so they drop into the `Orchestrator` unchanged; the Develop
  tool loop uses OpenAI function-calling instead of Anthropic tool-use blocks. Gateway
  routing/metadata (a concept header, a project tag) rides on `extra_headers`; the served
  model is read back from `x-muchty-model`/`x-model` when present. stdlib-only — no SDK
  dependency (matching `CrossProviderLens`). `runners.openai_chat` is public.

  This is what makes routing a build through a model gateway a configuration choice rather
  than a fork: point `base_url` at the gateway and the whole reasoning + code-writing line
  runs through it, with per-provider cost/routing and BYOK billing for the build phase.

## [0.5.0] — 2026-09-02

### Added

- **`Orchestrator.run(feature, block_on_unresolved=True)` — an advisory human gate for
  autonomous runs.** The Disambiguate station is deliberately adversarial (it will keep
  finding underspecified axes; a more complete brief tends to yield *more* questions, not
  fewer), and the default gate blocks the line before Design on any unresolved question —
  the right behaviour when a human is in the loop. Passing `block_on_unresolved=False`
  keeps recording those questions on `report.disambiguation` but lets the line **build on
  the versioned product intent**, moving the human judgement to the concrete PR (its gates
  and the merge) instead of a set of abstract pre-build questions. The default is unchanged,
  so existing callers still get the blocking gate.

## [0.4.2] — 2026-09-02

### Fixed

- **A model that rejects `effort` no longer sinks the run either.** 0.4.1 handled the
  `thinking` param; the very next live run showed the Haiku `Understand` station also
  rejects the `output_config.effort` knob (`400 - This model does not support the
  effort parameter`). `create_message` now strips *whichever* uniformly-sent param a
  400 names — `thinking` (top level) or `effort` (inside `output_config`, preserving
  the rest, e.g. the json-schema `format`) — and retries, bounded. Any error that
  isn't a droppable-param 400 still propagates unchanged.

### Changed

- `create_message(client, base_kwargs, thinking=None)` now returns just the response
  (was `(response, thinking_accepted)`) and is **stateless** — each call degrades
  independently, so an Opus station still gets full thinking/effort even after a Haiku
  station in the same run degraded. The per-runner `_thinking_supported` flag is gone.
  New helper `runners._strip_unsupported`.

## [0.4.1] — 2026-09-02

### Fixed

- **Thinking is no longer hard-wired on — the pipeline survives a model that doesn't
  support it.** Both runners sent `thinking={"type": "adaptive"}` on *every* station,
  but the roster runs `Understand` (ST-01) on `claude-haiku-4-5`, which rejects that
  param with `400 - adaptive thinking is not supported on this model`. A live run
  therefore died at the very first station. Now, when a model rejects the thinking
  param specifically, the call retries once without it and the runner stops sending it
  for the rest of the process; any other 4xx still propagates unchanged. A run on a
  provisioned key works out of the box again, with no configuration.

### Added

- **`FASTPDLC_THINKING` env var and a `thinking=` runner argument** to control extended
  thinking explicitly. Precedence: an explicit `thinking=` passed to `ClaudeRunner` /
  `CodingRunner` (including `None`) wins; otherwise `FASTPDLC_THINKING`; otherwise
  adaptive. Env values: `adaptive` (default), `off`/`none`/`0`/empty to omit, or
  `enabled:<budget_tokens>` for fixed-budget extended thinking. `runners.resolve_thinking`
  and `runners.create_message` (the graceful-degrade `messages.create` wrapper) are public.

## [0.4.0] — 2026-08-24

### Added

- **ST-04b Clean** — a simplification station between Develop and Test. An agent
  that has just solved a problem leaves the shape of the struggle in the code, and
  nothing downstream ever asked whether that was the simplest form of it. Test
  checks the behaviour is right; nobody checked the code was clean.

  Deliberately narrow: no new behaviour, no changed signatures, no new dependencies.
  A pass allowed to "improve while it is in there" is a second Develop station
  wearing a different hat, and its changes would arrive untested.

  `behaviour_preserved` is treated as a *claim*, not a fact. A Cleaner that admits
  it could not preserve behaviour has its work dropped and the admission recorded —
  it does not fail the run, and it does not get to ship either.

  Skip it with `--no-clean` (one fewer model call per run).

- `CLEAN_SCHEMA` exported from the package root.

### Notes

The station is **inserted, not renumbered**. ST-05 through ST-10 are referenced in
decks, diagrams and prose elsewhere, and renumbering a stable reference to make room
is the same mistake as renumbering a diagnostic code — so the new station is `ST-04b`
and a test asserts the rest of the roster is unmoved.

Prompted by Robert Martin's five-agent assembly line (Specifier, Coder, Cleaner,
Hardener, QA). Of the three we lacked, Cleaner was the real gap. **Hardener** —
mutation-testing the tests by actually breaking the code — needs a station with a
shell, which is a materially larger security decision than the current file sandbox
and is not taken here. **QA** driving a deployed application is a test framework, not
a validator; pulling it in would blur the line the product rests on.

## [0.3.1] — 2026-08-24

Housekeeping. **No behaviour change** — `0.3.0` and `0.3.1` are identical to import
and run, and the only differences are import ordering and variable names.

`0.3.0` was published from a commit whose CI was failing. A `ruff` gate was added to
CI without the code having been made to pass it first, so the lint step went red on
its very first run — while the publish was in flight. Nothing shipped broken: all 58
tests passed throughout and every finding was style rather than behaviour. But a
released tag should point at green CI, so this is that tag.

### Changed

- Lint clean under `ruff`. Two of the fixes earn their place rather than merely
  silencing a rule: `zip()` over the lens names and their results now passes
  `strict=True`, which is a real assertion that the two lists cannot silently
  diverge, and the variable `l` is renamed because it is indistinguishable from `1`
  in most fonts.

## [0.3.0] — 2026-08-24

Quality and ergonomics. No breaking changes: every existing command behaves as it
did, and the additions are opt-in flags.

### Added

- **`fastpdlc validate --json`** — findings as structured output against a
  `fastpdlc-report/1` schema. Diagnostic codes were already an API; making a
  consumer regex the prose to find one defeated the point of having them.
- **`fastpdlc evidence --verify RECORD`** — recomputes every digest in a record and
  reports what no longer matches. Content-addressing is only worth something if
  somebody can check it; producing a record nobody can verify is a claim, not
  evidence. Needs no key, no trust in the issuer and no network.
- **Orchestrator runs are kept** at `.fastpdlc/runs/<id>-<timestamp>.json`. A run
  refuted after two repair rounds holds the four verdicts and their failing cases —
  the most useful thing it produced. Discarding it because nothing was proposed was
  backwards.
- An **opt-in integration test** (`pytest -m integration`, needs `ANTHROPIC_API_KEY`)
  that exercises one cheap station against the real endpoint. Everything else stubs
  the model, which meant an API change would have broken users rather than CI.

### Changed

- **`PAC-060` now names what drifted.** "the bundle is stale" tells you to run a
  command; "2 artifact(s) differ: +BR-idempotent, TERM-ledger" tells you whether it
  is the change you meant to make, which is the question a reviewer actually has.
  Additions are prefixed `+`, removals `-`.

### Quality

- Library coverage **72% → 90%**, 28 → 58 tests, concentrated where it was thinnest:
  the CLI (30 → 80%), the plugin loader (62 → 97%), the coding sandbox (40 → 82%)
  and the runners (52 → 81%).
- Python 3.10 compatibility verified by parsing every module at that feature level,
  rather than assumed from the classifier list.
- `ruff` config and an 85% coverage floor in CI. The floor exists to stop coverage
  rotting, not to be gamed upward.

## [0.2.1] — 2026-08-23

Packaging only. No library changes — `0.2.0` and `0.2.1` are identical to import
and run.

### Changed

- **The sdist ships only the package.** `0.2.0`'s source distribution defaulted to
  "everything not gitignored", which included the marketing site, the Terraform and
  the deploy config — 125 files, 221 KB. It contained no secrets, but a published
  artifact should not depend on a `.gitignore` staying correct forever, and a PyPI
  version can be yanked and never replaced. The sdist is now an allowlist: 30
  files, 42 KB, with no `site/`, `infra/` or `.fastpdlc/`.
- `0.2.0` is yanked in favour of this release. It is safe — nothing secret was ever
  in it — but there is no reason to keep distributing the wider tarball.

### Added

- `scripts/check_no_secrets.py` — refuses credential-shaped strings in the package
  tree, and with `--dist` in the built artifacts, plus any operational path in the
  sdist. Runs in CI on every push and in the publish workflow immediately before
  upload, which is the last moment a leak is still recallable.

## [0.2.0] — 2026-08-23

Two new surfaces on top of the compiler and the gate. `build` and `validate` are
unchanged: same two runtime dependencies, no network, still the thing CI runs.

### Added

- **`fastpdlc orchestrate`** — the agent-built lifecycle over one artifact:
  Understand → Disambiguate → Design → Develop → Test → adversarial Verify, with a
  bounded repair loop. Control flow is deterministic; reasoning happens inside a
  station. Requires the new `agents` extra.
- **Four refuting lenses** at Verify — correctness, coverage, security, reproduce —
  running in parallel, each defaulting to *refuted* unless convinced. Minor findings
  deliberately do not block: a gate that fires on nitpicks gets bypassed.
- **`--cross-provider`** adds a fifth verdict from a non-Claude model via OpenRouter,
  so the critic cannot share the builder's blind spots. Uses stdlib `urllib`, so the
  core gains no dependency. Skipped without `OPENROUTER_API_KEY`; abstains rather
  than blocking if the call fails.
- **`--write`** lets the Develop station edit files through a bounded tool loop
  (list, read, write) confined to the project root. Containment is checked after path
  resolution, so `..`, absolute paths and symlink escapes are refused rather than
  sanitised. No shell, no network, no delete, no rename. Off by default.
- **`--dry-run`** exercises the whole pipeline offline with no model calls.
- **The human gate as a file** — `.fastpdlc/disambiguations/<id>.json`. Run one writes
  the open questions and stops, a person fills in each `answer`, run two proceeds. A
  blocking human gate cannot live inside one autonomous run, so it is two-phase by
  construction. `--resolve id=answer` does the same inline.
- **`fastpdlc evidence`** — a content-addressed record of what was checked, when, on
  which commit, and with what result. Every artifact, the config and the bundle carry
  a SHA-256, so a record is verified by recomputing digests rather than by trusting
  its issuer. Exit code follows `validate`, so CI can gate and record in one step.
- **`agents` extra** — `pip install 'fastpdlc[agents]'` pulls in `anthropic`. Nothing
  else in the library needs it.
- Public API: `Orchestrator`, `Runner`, `Station`, `StubRunner`, `Verdict`, `ROSTER`,
  `LENSES`, `read_resolutions`, `write_questions`, `build_record` are exported from
  the package root.

### Fixed

- YAML parses an unquoted `date: 2026-02-04` into a `datetime.date`, which
  `json.dumps` could not serialize — any project with a date field in frontmatter hit
  this. Bundles now emit ISO-8601 strings. Found by using the tool on its own blog.

### Notes

The orchestrator cannot merge: its terminal state is a report, and every station past
the gate is deterministic or human by construction. It also cannot run tests — Develop
has no shell — so a passing test report is a *claim* your CI still has to check.
Assembling a pull request and reading production back into intent are the caller's
job; the library has no git and no network.

## [0.1.0] — 2026-08-22

First release. The engine extracted from the pharthing / KibiPay payments platform,
verified by a byte-identical parity test.

### Added

- `fastpdlc build` — compile typed artifacts into one deterministic JSON bundle
  (sorted keys, fixed formatting, no timestamps).
- `fastpdlc validate` — schema, id integrity, cross-references and staleness. Exit
  code is the CI gate.
- Diagnostic codes: `PAC-001` required field, `PAC-010`/`011`/`012` id integrity,
  `PAC-020` reference resolution, `PAC-030` enum membership, `PAC-060` bundle
  staleness.
- Plugins — project validators, bundle transformers, extra staleness-gated outputs,
  and custom diagnostic codes in a project range.
- A reusable GitHub Action and a copier template.
- LGPL-3.0-or-later: copyleft on the engine, and importing it as a library does not
  place your project under the LGPL.

[Unreleased]: https://github.com/tarvitave/fastpdlc/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/tarvitave/fastpdlc/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/tarvitave/fastpdlc/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/tarvitave/fastpdlc/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/tarvitave/fastpdlc/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/tarvitave/fastpdlc/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/tarvitave/fastpdlc/releases/tag/v0.1.0
