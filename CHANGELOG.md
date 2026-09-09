# Changelog

All notable changes to FastPDLC. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows
[semantic versioning](https://semver.org/).

**Diagnostic codes are API.** A `PAC-NNN` is never renumbered — a check that changes
meaning gets a new code and the old one is retired. Changing the JSON bundle shape, a
config key, or the plugin `Registry` surface is a breaking change and bumps the major.

## [Unreleased]

### Added

- **`fastpdlc validate --watch`** — the same gate, re-run whenever a `product/` file,
  the config or the committed bundle changes. Polling, so the core keeps its two
  dependencies. Not a gate: it never exits non-zero, because a red tree you are
  mid-fix should not kill the terminal you are fixing it in.

- **`fastpdlc lsp`** — a language server over the product graph: diagnostics,
  completion, hover, go-to-definition, find-references, workspace symbols. Needs
  `pip install 'fastpdlc[lsp]'`. A VS Code client lives in `editors/vscode/` and is
  deliberately a shim — it launches the server and owns no logic.

  Completion offers only values the validator would accept, because it reads the same
  config: the ids of the type a reference field must resolve to, or an enum's members.

  Diagnostics are `validate`'s, computed from the files **on disk** — so they refresh
  on save, not per keystroke. An editor validating the unsaved buffer would be a
  second opinion about correctness, and this project cannot have two judges.

- **`fastpdlc mcp`** — the same graph as six read-only tools for a coding agent:
  `product_schema`, `product_list`, `product_get`, `product_allowed_values`,
  `product_references_to`, `product_validate`. Needs `pip install 'fastpdlc[mcp]'`.
  Read-only on purpose: a server that could also write would let the thing being
  judged edit the evidence.

- **`fastpdlc.index`** — the resolved graph with source positions, shared by both
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
