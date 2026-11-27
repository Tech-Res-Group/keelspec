# KeelSpec

**Product-as-code as a validated graph — for any project.**

Your product intent — the glossary, the constraints, the business rules, the
features, the decisions — usually lives as hopeful markdown that quietly rots. KeelSpec
turns it into **code**: you declare your typed artifacts in one config file, and it
loads them, enforces the schema and the cross-references, compiles a JSON bundle your
app or docs can render, and **fails CI when the committed bundle drifts**.

It started as the product-as-code engine inside a payments platform and was extracted
so any team can use it.

### What it covers, and what it does not

KeelSpec governs the **engineering segment** of delivery: from a story whose intent is
written down to a proposed change that has been built, tested and attacked. It is not
an end-to-end product delivery model, and it does not claim to be one.

| | covered here | where it is covered instead |
|---|---|---|
| **Before the story** — problem selection, value, funding, prioritisation | The story must trace to an `outcome` with a metric and an owner; it cannot pretend to have none (`PAC-002`, `PAC-903`). | Portfolio and product management |
| **The spec** | Typed, validated, cross-referenced; open questions stop the line; named roles accept it before design. | — |
| **Story → PR** | The agent-built line, with adversarial verification and triage. | — |
| **After the PR** — integration, UAT, release, operations, adoption | A `shipped` feature must carry an owner, rollback and runbook, and NFR evidence (`PAC-904`, `PAC-905`). | CD pipeline, change management, operations |
| **Business outcome** | The link from feature to outcome, so it can be measured. | Production analytics |

The stations after the PR (ST-07 to ST-10) are hand-off points, not automation. What
the line *does* own, it proves: every claim above is a diagnostic code or a test. See
[AI-GOVERNANCE.md](AI-GOVERNANCE.md) for what the agent-built line does with models
and data, and what is left to your organisation's policy.

```bash
pip install keelspec
```

## Quickstart

1. Describe your artifact types in `product.config.yaml`:

   ```yaml
   product_dir: product
   output: build/product.generated.json
   types:
     - name: terms                 # a glossary
       dir: terms
       id_prefix: "TERM-"          # ids must be TERM-<slug> and match the filename
       required: [id, term, definition]
       fields: [term, definition, see_also]
       references:
         - field: see_also         # every see_also must resolve to another term
           to: terms
     - name: rules                 # the durable invariants
       dir: rules
       id_prefix: "BR-"
       required: [id, title, statement]
       fields: [title, statement]
   ```

2. Author artifacts as markdown-with-frontmatter under `product/`:

   ```markdown
   ---
   id: TERM-payment
   term: Payment
   definition: An instruction to move money between two parties.
   see_also: [TERM-ledger]
   ---
   The canonical unit of work in the system.
   ```

3. Build the bundle and gate it in CI:

   ```bash
   keelspec build       # -> build/product.generated.json  (commit it)
   keelspec validate    # schema + graph + staleness; non-zero exit on errors
   ```

## While you author

The gate is deterministic, which means everything it knows is available before you
push. Four surfaces expose the same graph, and **none of them forms its own opinion**
— every verdict below is `validate`'s, unchanged. An editor that said green while CI
said `PAC-020` would be a second judge, and a project whose whole claim is a
deterministic gate cannot afford two.

```bash
keelspec validate --watch          # the gate, re-run on every save
keelspec lsp                       # language server (pip install 'keelspec[lsp]')
keelspec mcp                       # the graph as tools (pip install 'keelspec[mcp]')
```

### `--watch`

Re-validates whenever a `product/` file, the config, or the committed bundle
changes. No extra dependency; it polls. Deliberately **not** a gate — it never exits
non-zero, so a red tree you are mid-fix does not kill the terminal you are fixing it
in. CI runs plain `validate`.

### The language server

Diagnostics, completion, hover, go-to-definition, find-references and workspace
symbols over your `product/` tree, in any LSP client — VS Code, JetBrains, Neovim,
Zed. A VS Code client lives in [`editors/vscode/`](editors/vscode/); it launches this
and owns no logic of its own.

Completion is the load-bearing one: in a reference field it offers the ids of the
type that field must resolve to, and in an enum field its members — both read from
the same config the validator reads, so **an accepted completion cannot be a
`PAC-020` or a `PAC-030`**. Hover shows what an id means and how many artifacts point
at it; find-references answers "what breaks if I retire this rule?".

Diagnostics come from the file *on disk*, so they refresh on **save** rather than on
every keystroke. That is the trade for having one judge. Completion, hover and
navigation do read the unsaved buffer, because they answer "what is here?" rather
than "is this allowed?".

### The MCP server

The same graph, spoken to an agent rather than an editor — because in a repo run this
way the author of `product/features/refunds.md` is increasingly a model, and asked
for a `constraints` list it will happily invent `CON-refund-window`.

Six read-only tools: `product_schema`, `product_list`, `product_get`,
`product_allowed_values`, `product_references_to` and `product_validate`. Read-only
on purpose — an agent proposes with its own tools, and a server that could also write
would let the thing being judged edit the evidence.

```json
{ "mcpServers": { "keelspec": { "command": "keelspec", "args": ["mcp"] } } }
```

## Tickets in, without giving up the source of truth

```bash
keelspec intake https://github.com/acme/pay/issues/7   # or acme/pay#7
keelspec intake PAY-123                               # Jira (JIRA_BASE_URL)
keelspec intake --sync                                # what changed upstream?
keelspec intake --sync --apply                        # write it, on a branch
```

`intake` writes a draft feature from a GitHub issue or a Jira ticket: the title, the
bullets under its "Acceptance criteria" heading as bare-string criteria, and the
description in a marked block in the body. The id comes from the ticket key, so
renaming the ticket never renames the feature.

**The feature file is the source of truth.** Every later change to the ticket must
reach the file, but only as a proposal: `--sync` shows the diff for every ticket that
moved, and `--apply` writes it and refuses to on the default branch. Commit it on a
branch and merge it through the gate like any other change. Run it on a schedule or
from a tracker webhook; the result is the same.

The ticket owns three things: the title, the criteria and the description block.
Everything else (status, outcome, NFRs, prose outside the block, a criterion a person
has tied to a test) is never touched. Where a person and the ticket have both changed
the same owned field since the last sync, sync stops and says so. It never picks a
winner. What was last synced lives in `.keelspec/intake/<feature>.json`; commit it.

Credentials come from the environment only: `GH_TOKEN` or `GITHUB_TOKEN`, and
`JIRA_BASE_URL` with `JIRA_EMAIL` + `JIRA_API_TOKEN` or `JIRA_PAT`. No ticket content is
sent to a model. Optional config:

```yaml
intake:
  type: features          # the artifact type to write (default: features)
  link_field: ticket      # a frontmatter field for the ticket URL (default: in the body)
  status: idea            # the draft status (default: idea, or the first enum value)
```

## The agent-built lifecycle

`keelspec orchestrate` runs a station line over one artifact: **Understand →
Disambiguate (human gate) → Design → Develop → Clean → Test → adversarial Verify →
Triage**, with a bounded repair loop.

```bash
keelspec orchestrate FEAT-refunds                  # needs ANTHROPIC_API_KEY
keelspec orchestrate FEAT-refunds --no-clean       # skip the simplification pass
keelspec orchestrate FEAT-refunds --dry-run        # offline; exercises the pipeline
pip install 'keelspec[agents]'                     # the reasoning stations
```

Five critics attack the result through independent lenses — **correctness,
coverage, security, reproduce, integrity** — each defaulting to *refuted* unless
convinced. The first four ask whether the change meets its specification.
**Integrity** asks whether the business process around it survives: upstream and
downstream flows, exception and recovery paths, reconciliation, reporting, and the
rules and NFRs in the product context. Every critic sees the feature's linked
artifacts, not just its id.

### When it is refuted: triage before repair

A refuted change is not automatically sent back to the developer. **ST-06b Triage**
first decides *why* it failed: `requirement`, `design`, `dependency`, `environment`,
`implementation`, `model` or `business_decision`. Only an implementation fault is
repaired automatically. Every other cause ends the run as **`needs-human`**, with the
question a person has to answer, because a defective requirement repaired twice is
still a defective requirement. After `--max-repair` rounds the run reports honestly
rather than proposing, and says what kind of failure it was.

### Risk tiers, not "is it critical?"

How much of the line a feature gets is scored from the feature itself.
`product.config.yaml` declares which fields count and by how much, and what each tier
requires:

```yaml
delivery:
  risk_factors:
    customer_impact: {high: 3, medium: 1}
    data: {pii: 3, financial: 3, internal: 1}
    reversible: {false: 3}
  tiers:
    - name: high
      min_score: 5
      approvers: [product-owner, engineering-owner, security]
      independent_critic: true   # a critic from another vendor than the builder
    - name: standard
      min_score: 2
      approvers: [product-owner]
    - name: light            # the old "spike": fewer lenses, no Clean, one repair
      min_score: 0
      lenses: [correctness, coverage, security]
      clean: false
      max_repair: 1
```

The score, the tier and every contribution to it are recorded on the run. A feature
that cannot be found is assessed at the highest tier, because unknown risk is not low
risk.

### The human gate

Open questions stop the line *before* design — building the wrong thing correctly is
the expensive failure. A blocking human gate cannot live inside one autonomous run,
so it is two-phase: run 1 writes the questions to
`.keelspec/disambiguations/<id>.json` and stops, a person fills in each `answer`,
run 2 reads them and proceeds.

```json
{
  "status": "pending",
  "questions": [
    { "id": "q1", "dimension": "refund window start",
      "question": "From authorization, settlement or delivery?", "answer": "" }
  ]
}
```

`--resolve q1="from settlement"` does the same thing inline for one-offs.

**"A human was in the loop" is not accountability.** When the feature's risk tier
names `approvers`, the gate file gets one slot per role, and Design does not start
until each role has a name against it:

```json
"approvals": [
  { "role": "product-owner", "by": "Avery Chen", "at": "2026-10-04T09:00:00Z" },
  { "role": "security", "by": "", "at": "" }
]
```

`--approve security="Sam Lee"` signs inline. Unlike open questions, a required
approval cannot be made advisory: an autonomous run does not get to decide that
nobody needs to accept the spec. The name is self-asserted, so commit the gate file:
the commit that fills in `by` is the signature.

### Writing code

`Develop` is the only station that needs tools, so it runs a bounded loop with three
of them — list, read, write — confined to the project root. Absolute paths, `..` and
symlink escapes are refused, not sanitised; there is no shell, no network, and no
delete.

```bash
keelspec orchestrate FEAT-refunds            # proposes a diff, writes nothing
keelspec orchestrate FEAT-refunds --write    # lets it edit your working tree
```

`--write` is opt-in on purpose. Run it on a clean branch.

### Bring your own builder

```bash
keelspec orchestrate FEAT-refunds --builder claude-code   # or: --builder codex
keelspec orchestrate FEAT-refunds --builder codex --write # apply it if proposed
```

Develop, its repairs and Clean run through that agent's own CLI (`claude -p` or
`codex exec`); every other station is unchanged, so the same Test station, critics and
Triage judge it. An external agent brings its own shell, so the built-in sandbox
cannot vouch for it. The guarantee moves to the diff instead:

- The agent works in a **throwaway git worktree** at `HEAD`, never in your tree.
  Uncommitted changes are not visible to it.
- **What changed is read from git**, not from the agent's account of it, and the
  reviewers get the real diff.
- A step that touches a **protected path** (the product directory, the committed
  bundle, the config, the plugin, `.keelspec/`, or CI configuration) is rolled back
  and fails the run. The thing being judged does not edit what it is judged against.
- The change is saved as `.keelspec/runs/<feature>-<stamp>.patch`. `--write` applies
  it to your working tree, and only when the line proposes it.

**Credentials are the agent's, not KeelSpec's.** The CLI authenticates however it is
already set up: a personal login on a laptop, or an API key or service account in CI.
The run record names the builder, its version and the base commit. Claude Code runs
with its shell and web tools disabled; Codex runs in its own `workspace-write`
sandbox. When the builder and the critics share a vendor, the run says so; add
`--cross-provider` for a critic outside the builder's family.

Devin and Copilot's coding agent work asynchronously, through a pull request, and
are not supported yet.

### A critic that does not share the builder's blind spots

```bash
OPENROUTER_API_KEY=... keelspec orchestrate FEAT-refunds --cross-provider
```

Adds a sixth verdict from a non-Claude model, joining the same refute/repair logic.
Diversity is a correctness lever: a critic from the same family can share the
builder's failure modes. Without the key the lens is skipped and the run is
identical to native-only; if the call fails it abstains rather than blocking.

### What is structural

- **Nothing merges.** The orchestrator's terminal state is a report. `validate` is
  the judge and a human decides; every station past the gate is deterministic or
  human by construction, and a test asserts it.
- **Minor findings do not block.** A gate that fires on nitpicks trains people to
  bypass it, and a bypassed gate is worse than none.
- **An unreachable critic abstains.** One flaky provider must not become an outage.
  The same goes for triage: if it cannot answer, the line repairs as it did before.

Control flow is ordinary code; reasoning lives inside a station. Supply your own
`Runner` to change what any station does.

### What the line has been doing

```bash
keelspec runs          # status mix, first-pass rate, refutations by lens,
keelspec runs --json   # triage causes, risk tiers, median run time, and:
```

- **Rejection rate per lens**: of the runs where a critic cast a verdict, the share it
  refuted at least once. Abstentions are counted separately, never as passes.
- **Review load**: needs-human and blocked runs, questions asked at the human gate,
  and required approvals given or still missing, per feature and in total.
- **Cost**, and **cost per merged PR**. Each run records tokens per model call (counts
  only, no prompts). Prices are yours, in `product.config.yaml`; KeelSpec ships none:

  ```yaml
  prices:                       # USD per million tokens, from your contract
    claude-opus-5: {input_per_mtok: 0, output_per_mtok: 0}
  ```

  A vendor that reports its own cost (an external builder) is taken at its word. A
  run with any call that cannot be priced either way is reported as unpriced, never
  guessed. A proposed run prints a `KeelSpec-Run: <run id>` trailer; put it on the
  commit, and a run counts as merged once that commit is reachable from `HEAD`. Cost
  per merged PR includes the failed attempts at the same feature.
- **Spec drift**: the share of kept evidence records whose findings include `PAC-060`,
  and the share that failed the gate. Keep the record CI makes, e.g.
  `keelspec evidence -o .keelspec/evidence/$(date -u +%Y%m%dT%H%M%SZ).json`, or point
  `--evidence DIR` at wherever your CI keeps them.

Every run is kept under `.keelspec/runs/`. The schema is `keelspec-metrics/2`; every
`/1` field is unchanged. These numbers measure the line, not the business. Whether
what it shipped mattered is measured in production, against the `outcome` each
feature traces to.

## Governed agents

The same product graph can declare an agent that runs in production, not just the
agents that build your code. You declare the agent, the tools it may call, the
policies that decide each call, and the scenarios it must pass, all as markdown
artifacts in the repository. KeelSpec validates them, replays the scenarios in CI,
and runs the agent with every tool call decided by policy first.

```yaml
# product.config.yaml
presets: [agents]          # adds AGENT-, TOOL-, POL- and SCN- types and their checks
```

The reference project is `examples/payments-exceptions/`: one agent that
investigates rejected payments, three MCP tool servers (a payments ledger, an
ISO 20022 parser, case management), five policies and three scenarios, including
one where remittance text tries to instruct the agent to release funds.

```bash
cd examples/payments-exceptions
keelspec validate                                   # PAC-070..077 among the checks
keelspec policy explain AGENT-payment-exceptions TOOL-case-management release_funds '{}'
keelspec simulate                                   # three scenarios, offline, no API key
keelspec tools check                                # each MCP server matches its artifact
pip install 'keelspec[runtime]'
keelspec run AGENT-payment-exceptions "Case 88121: pacs.002 RJCT AC04 on E2E-77F"
keelspec approvals approve <run> <step> --by <name> && keelspec run --resume <run>
```

What holds, and is tested:

- **Only declared operations are offered to the model**, and every call is decided
  by the agent's policies before it runs: deny beats approval beats redact beats
  allow, and no matching policy means deny. `require_approval` pauses the run until
  a person signs.
- **The runtime runs the committed bundle** and refuses one that fails validation
  or is stale (PAC-079). A tool server whose tool list differs from its artifact
  refuses the run (PAC-073).
- **Run records carry no content**: ids, decisions, outcomes and token counts. Content
  is written to a separate file only when you turn capture on, and the record says
  so. OpenTelemetry spans follow the same rule (`docs/observability.md`).
- **A router refusal stops the run** (no retry, no quiet downgrade). The model is
  reached over HTTP through FifeRouter or any OpenAI-compatible endpoint.
- **There is no default model endpoint.** `router.base_url` in
  `keelspec.runtime.yaml` says where prompts may go (hosted FifeRouter, a
  self-hosted router, or your own gateway), and `run` and `serve` refuse to start
  until it is set.
- **`keelspec simulate` replays scenarios with a deliberately naive scripted model**
  that obeys instructions it finds in tool data, so a passing injection scenario
  shows the policy held, not that a model behaved. `--evidence` records the result,
  and an agent marked `deployed` without passing evidence is an error (PAC-076).
- **`keelspec orchestrate AGENT-x`** adds a Tools station that scaffolds missing MCP
  servers, and a `policy` lens that searches for arguments or injected text that
  would run a guarded or money operation with no person in the loop.
- **`keelspec serve`** puts deployed agents behind an HTTP API (or MCP), with a
  separate approver token so whoever starts a run cannot approve it.
  `infra/agent-runtime/` has a container recipe.

What it is not: a hosted service, a visual agent builder, or a guarantee about what a
model will say. It governs what an agent can *do*: which calls run, which wait for a
person, and what the record shows afterwards.

## Evidence

`keelspec evidence` emits a content-addressed record of what was checked, when, on
which commit, and with what result — for the audit conversation that starts *"prove
your documented rules matched your implementation"*:

```bash
keelspec evidence -o build/evidence.json      # make a record
keelspec evidence --verify build/evidence.json # check one against this tree
```

Every artifact, the config and the bundle carry a SHA-256, so the record is verified
by recomputing digests rather than by trusting whoever produced it. Historical
evidence needs no special support: check out the commit and run it again — bundles
are byte-stable, so the digests match. Exit code follows `validate`, so it gates CI
and records it in one step.

## What `validate` enforces

Every finding carries a stable `PAC-NNN` code (an API — CI and dashboards match on the
code, never the prose):

| code | meaning |
|---|---|
| `PAC-001` | an artifact is missing a required field |
| `PAC-002` | a recommended field is empty (a warning; never gates) |
| `PAC-010` | an id doesn't start with its type's `id_prefix` |
| `PAC-011` | an id doesn't match its filename |
| `PAC-012` | a duplicate id within a type |
| `PAC-020` | a reference field doesn't resolve to a known artifact |
| `PAC-030` | a field value isn't in the type's allowed set (`enums`) |
| `PAC-060` | the committed generated bundle is missing or stale |

## Config reference

Each entry under `types`:

- **`name`** — the collection name (and the key in the bundle).
- **`dir`** — the subdirectory under `product_dir`.
- **`id_prefix`** *(optional)* — required id prefix; with **`id_matches_filename`**
  (default `true`), the id must equal the filename stem.
- **`required`** — frontmatter fields that must be present and non-empty (`id` always is).
- **`recommended`** — fields that should be present; an empty one is a `PAC-002` warning.
- **`fields`** — the fields captured into the bundle.
- **`enums`** — `field -> [allowed values]`.
- **`references`** — `[{ field, to }]`: values of `field` must be the id of a `to` artifact.

Optional, at the top level:

- **`delivery`** — the risk model `keelspec orchestrate` applies.
  **`risk_factors`** maps a field to the score each of its values adds; **`tiers`**
  lists `{name, min_score, approvers, lenses, clean, max_repair, independent_critic}`,
  and the highest tier the score reaches applies. `independent_critic: true` refuses
  to run unless at least one critic comes from a different model vendor than the
  builder: `--cross-provider`, or a builder such as `codex` when the critics are
  Claude. Unset tier fields keep the line's default.

## Extending it — plugins

Real projects need more than schema: cross-file checks ("does this `links.code` path
exist?"), derived bundle fields (reverse edges, rollups), extra generated outputs (a
runtime catalogue), and their own diagnostic codes. A **plugin** registers those without
forking the engine — which is how a large project migrates onto KeelSpec with **no loss
of functionality**:

```python
# product_hooks.py
from keelspec import register

def register(reg):
    register("PAC-900", "links.code path does not exist on disk")

    @reg.validator
    def code_paths_exist(bundle, config, root, report):
        for f in bundle["features"]:
            for path in f.get("code") or []:
                if not (root / path).exists():
                    report.add("PAC-900", f"missing {path}", f["_file"])

    @reg.bundle_transformer
    def reverse_edges(bundle, config, root):
        ...  # enrich the bundle in place

    reg.extra_output("build/catalogue.json", render_catalogue)  # staleness-gated too
```

```bash
keelspec -p product_hooks.py validate
```

## Start a new repo in one command

Scaffold a ready-to-go product-as-code repo (config, example artifacts, and the CI
gate) with the [copier](https://copier.readthedocs.io) template:

```bash
pipx run copier copy --trust gh:Tech-Res-Group/keelspec my-product-repo
```

`--trust` lets the template run `keelspec build` once so the new repo is valid on its
first commit.

## CI

Use the reusable Action — it installs KeelSpec and runs the gate:

```yaml
# .github/workflows/product.yml
name: product-as-code
on: [pull_request, push]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Tech-Res-Group/keelspec@v1.0.1
        with:
          config: product.config.yaml     # optional (default)
          plugin: product_hooks.py         # optional project checks
```

<details><summary>Prefer plain pip?</summary>

```yaml
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install keelspec
      - run: keelspec validate
```
</details>

## Used in production

KeelSpec is the product-as-code engine of the **pharthing / KibiPay** payments
platform (50 features, a concept catalogue, 70 decisions, and a ~490 KB render bundle). pharthing's
CI runs `keelspec validate` as its sole gate via a plugin that adds domain checks — a
byte-identical parity test proves nothing was lost in the extraction. That's the
plugin system above, doing real work.

## Releasing

Publishing to PyPI is automated via GitHub Releases + Trusted Publishing — see
[RELEASING.md](RELEASING.md). Changes per version are in
[CHANGELOG.md](CHANGELOG.md).

## License

Apache-2.0. Permissive: use it, embed it, ship it, no obligations back beyond the
notice. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Versions up to 0.6.3 were published as `fastpdlc` under LGPL-3.0-or-later. That
package has been removed from PyPI; `keelspec` is the only name.
