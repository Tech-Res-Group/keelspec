---
title: KeelSpec — The gate for software factories
description: Bring any agent fleet. KeelSpec keeps product intent as typed, versioned source, gates every pull request with a deterministic check that calls no model, and records evidence you can verify. Agents propose, gates enforce, a human merges.
url: https://keelspec.com/
---
The line — seven agent stations, two human gates, three deterministic

# The gate for software factories.

Bring any agent fleet: Claude Code, Codex, Devin, Copilot.
 **KeelSpec decides what merges.** Its gate calls no model and belongs
 to no agent vendor, so it can check all of them. Devin can't credibly check Devin,
 and Factory can't check Factory.

Agents propose, gates enforce, a human merges.

## Spec. Any agent. Gate.

KeelSpec owns the three things a builder should not own about its own
 work: the intent it is judged against, the check that judges it, and the record of
 what passed.

1. 01
 The spec
 Typed product intent, in your repo.
 Features, rules, decisions, whatever types you declare: markdown with typed frontmatter,
 validated as a graph and compiled into a committed bundle. Open questions stop the
 line before design, and named roles accept the spec.
 `PAC-060` fails the build when the committed bundle
 drifts from its sources.
1. 02
 Any agent
 The builder is swappable.
 Every station runs through one `Runner` seam. The library ships runners
 for the Anthropic API and for any OpenAI-compatible endpoint, such as your own model
 gateway, and you can supply your own. A pull request from any agent, or any
 person, meets the same gate.
 Roadmap Ready-made
 adapters for Claude Code, Codex, Devin and Copilot's coding agent.
1. 03
 The gate
 Deterministic first, then a person.
 `keelspec validate` calls no model. The same tree gets the same
 `PAC-NNN` verdict on every pull request, and the exit code is the
 contract. Inside the line, five critics try to refute each change, with an optional
 sixth on a different model provider.
 Nothing auto-merges. A human does.

## KeelSpec runs the FastPDLC lifecycle.

Ten stations from a written-down story to production. KeelSpec automates
 the engineering segment, from understanding the spec to a change that has been built,
 tested and attacked. Everything after the pull request is a hand-off to the process
 you already run.

1. ST-01
 Understand
 read the graph
 agent
1. ST-02
 Disambiguate
 human gate
 human
1. ST-03
 Design
 the Architect
 agent
1. ST-04
 Develop
 writes code
 agent**ST-04b** Clean · simplify, not change
1. ST-05
 Test
 coverage, by a separate author
 agent
1. ST-06
 Verify
 5 refuting lenses
 agent**ST-06b** Triage · why it failed

Triage sends only an
 **implementation** fault back to Develop, within a repair limit. A requirement,
 design, dependency, environment, model or business-decision fault stops the line
 for a person.

1. ST-07
 Assemble
 Your branch and PR tooling collects the change. The line hands over a report.
 deterministic
1. ST-08
 CI gates
 Your CI runs `keelspec validate` next to your own tests.
 deterministic
1. ST-09
 Human merge
 A person merges. KeelSpec never does.
 human
1. ST-10
 Production
 Your CD and operations. Measured against the outcome the feature traces to.
 deterministic

The scope is deliberate. See
 [the lifecycle page](/lifecycle.html) and
 [AI-GOVERNANCE.md](https://github.com/Tech-Res-Group/keelspec/blob/main/AI-GOVERNANCE.md) for what the line does
 with models and data.

## Five agent critics, each trying to refute the work.

The agent that builds a change does not get to grade it. A separate
 station attacks the result through five independent lenses, each defaulting to
 *refuted* unless convinced. Four ask whether the change meets its specification;
 the fifth asks whether the business process around it survives.

### correctness

Find an input where it does the WRONG thing — and do the tests pass vacuously?

### coverage

Does every acceptance criterion map to a test that would catch its regression?

### security

Payments lens: authz, trust boundaries, injection, PII, secrets, spend / consent.

### reproduce

Ignore the happy path: concurrency, partial failure, retries / idempotency, rollback.

### integrity

Every criterion passes — so which business scenario, exception path or downstream consumer does it still break?

`--cross-provider` adds a verdict from a model outside the builder's family,
 so it cannot share the builder's blind spots. It sees a diff summary and test notes,
 **without** product context. If the call fails, it abstains rather than
 blocking.

## The audit trail an SDLC or model-risk review asks for.

The review starts with
 *“prove your documented rules matched what you shipped.”* KeelSpec
 answers with files in your repository, checked by recomputing digests rather than by
 trusting whoever produced them.

- #
 **`keelspec evidence`**A content-addressed record: the commit,
 whether the tree was clean, the tool version, the config, a SHA-256 for every
 artifact and the bundle, every finding, and the result. Its exit code follows
 `validate`, so CI gates and records in one step.
- ✓
 **`--verify`**Recomputes every digest against the tree. For an
 old record, check out its commit and run it again: bundles are byte-stable.
- ✎
 **Run records and named approvals**Every orchestrated run keeps each
 station's output, every verdict, the triage cause and the risk tier. Required
 approvers sign the spec by role, and the commit that fills in the name is the
 signature.

KeelSpec produces evidence. It does not make you compliant and holds no
 certification. What the evidence must show is your organisation's policy.

## On top of your agents, not instead of them.

Devin, Factory.ai, Claude Code, Codex and Copilot's coding agent build
 software. KeelSpec does not compete with them on building. It is the part a builder
 cannot credibly supply for itself: a check it does not control.

### Your agent fleet brings

- The builder, and whatever runs it: sandboxes, parallel runs, IDE and chat
 integrations, ticket intake.
- Its own review and testing, if you use them.
- Its own pricing, hosting and enterprise terms.

### KeelSpec adds

- Typed, versioned intent the change is judged against, with `PAC-060`
 on drift.
- A gate that calls no model and belongs to no agent vendor or model provider.
- Five refuting critics, an optional sixth on a different model provider, and
 triage before repair.
- Evidence records that are verified by recomputation.
- All of it in your repo and your CI: `pip install keelspec`, a GitHub
 Action, Apache-2.0.

### KeelSpec does not

- Run agents in managed sandboxes or in the cloud.
- Replace your CI, CD or change management. ST-07 to ST-10 are hand-offs.
- Provide SSO, or hold SOC 2 or any other certification.
- Merge anything.

Not built yet: ready-made builder adapters for Claude Code, Codex, Devin and Copilot's
 coding agent, and intake that turns GitHub Issues, Linear or Jira tickets into feature
 files with acceptance criteria. Today, `keelspec runs` already reports
 first-pass rate and refutations by lens.

## The only product gate at a payments platform.

KeelSpec is the product-as-code engine of the
 **pharthing / KibiPay** payments platform. It was extracted from a working
 system so other teams could use it.

pharthing's CI runs **keelspec validate** as its sole product gate, through
 a plugin that adds its domain checks. A **byte-identical parity test** proves
 the extracted engine produces exactly the bundle the in-house one did.

[Read the case study](/blog/payments-case-study.html)

## Declare it. Author it. Gate it.

One config file, plain markdown artifacts, and a command whose exit
 code is the whole contract.

### Declare your types

There is no fixed schema. You name the collections, the required fields, the id
 prefixes, the allowed values, and which fields must resolve to other artifacts.

```
# product.config.yaml
product_dir: product
output: build/product.generated.json
types:
  - name: terms
    dir: terms
    id_prefix: "TERM-"
    required: [id, term, definition]
    fields: [term, definition, see_also]
    references:
      - field: see_also
        to: terms
```

### Author the artifacts

Markdown with YAML frontmatter, one file per artifact, in your repo, reviewed in
 pull requests like everything else. The prose below the fence is yours.

```
<!-- product/terms/TERM-payment.md -->
---
id: TERM-payment
term: Payment
definition: An instruction to move
  money between two parties.
see_also: [TERM-ledger]
---
The canonical unit of work in
the system.
```

### Gate the build

Compile the bundle, commit it, and let CI (continuous integration) prove it still matches the source.
 Non-zero exit means the pull request does not merge.

```
# .github/workflows/product.yml
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Tech-Res-Group/keelspec@v0.7.0
        with:
          config: product.config.yaml
          plugin: product_hooks.py
```

## Seven codes stand between you and drift.

These run on every pull request, including one an agent opened. Every finding carries a stable **PAC** (product-as-code)
 `PAC-NNN` code. Codes are an API — continuous
 integration (CI), dashboards and humans match on the code, never the prose. Existing
 codes are never renumbered.

### Required field

An artifact is missing a field its type declares as required.

### Id prefix

An id does not start with the `id_prefix` its type requires.

### Filename match

The id and the filename disagree, so the artifact can't be found by either.

### Duplicate id

Two artifacts in one collection claim the same id. References become ambiguous.

### Dangling reference

A reference field points at an artifact that does not exist. This is the one
 that catches renames and deletions before a reviewer ever opens the PR.

### Enum violation

A field value is outside the allowed set its type declares.

### Staleness — the one nobody else has

The committed bundle no longer matches the artifacts that produced it.
 Somebody edited the source and didn't rebuild, or edited the build and didn't
 touch the source. Either way, what you ship and what you wrote have parted
 company — and CI says so, in the diff, on the pull request.

Plugin outputs are staleness-gated too, so a generated catalogue or a runtime
 manifest can never quietly fall behind.

## Life of a pull request.

Someone renames one term. Here is what happens
 with KeelSpec in the loop — and what would have happened without it.

### A rename lands.

An engineer decides `TERM-payment` was always the wrong word and
 renames it to `TERM-charge` in a pull request. One file changed.
 Looks harmless.

### CI goes red before a human looks.

Three artifacts referenced the old id — two terms and a business rule. The
 graph no longer resolves, so the gate fails with the file and field named.

### The graph gets fixed, not the prose.

Three `see_also` values updated, `keelspec build` run
 once. The bundle regenerates deterministically — sorted keys, byte-stable
 output, so the diff is exactly the change and nothing else.

### Staleness clears.

The committed `product.generated.json` matches its sources again.
 Green. The reviewer now reviews a decision, not a consistency puzzle.

### Merged — and everything downstream already knows.

The docs site, the in-app glossary, the internal catalogue and the context you
 hand an LLM all render from the same bundle. Nobody wrote a migration doc.
 Nobody had to remember.

### Without the gate

The rename merges. Three documents keep pointing at a term that no longer
 exists. Nobody notices for eleven months, and by then two of them have been
 copied into a slide deck.

## Your checks. Your codes. No fork.

Real projects need more than schema. A plugin
 registers project-specific validators, enriches the bundle, and emits extra generated
 outputs — which is how a large codebase migrates onto KeelSpec with no loss of
 functionality.

- fn
 **Validators**Cross-file checks the config can't express — does this
 `links.code` path actually exist on disk?
- ⇄
 **Bundle transformers**Derived fields computed at build time: reverse
 edges, rollups, denormalised views your renderer wants.
- ⤓
 **Extra outputs**Emit a runtime catalogue or manifest alongside the
 bundle — and it is staleness-gated exactly like the bundle is.
- 9xx
 **Your own diagnostic codes**Register codes in a project range so they
 never collide with the core set. Your CI matches on them the same way.

```
# product_hooks.py
from keelspec import register

def register(reg):
    register("PAC-900", "links.code path does not exist")

    @reg.validator
    def code_paths_exist(bundle, config, root, report):
        for f in bundle["features"]:
            for path in f.get("code") or []:
                if not (root / path).exists():
                    report.add("PAC-900",
                               f"missing {path}",
                               f["_file"])

    @reg.bundle_transformer
    def reverse_edges(bundle, config, root):
        ...  # enrich the bundle in place

    reg.extra_output("build/catalogue.json", render)
```

## A valid product-as-code repo on its first commit.

The copier template scaffolds the config, example artifacts and the CI gate.
 `--trust` lets it run
 `keelspec build` once so
 the new repo is green before you've written a line.

## The obvious objections.

## Ship the gate this week.

Install it, declare two types, commit the bundle. The first
 `PAC-020` you catch will pay for the
 afternoon.
