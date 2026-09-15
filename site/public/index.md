---
title: KeelSpec — A workforce builds it. A gate judges it.
description: Product intent as versioned source, a workforce of agents building against it, and a deterministic PAC-NNN gate that judges every pull request. Agents propose, gates enforce, a human merges.
url: https://keelspec.com/
---
The line — six agent stations, two human gates, three deterministic

# A workforce builds it. A gate judges it.

Product intent lives as **versioned source**. A team of agents builds
 against it. Then a deterministic gate judges the result — the same
 `PAC-NNN` rubric on every pull request,
 including an agent's own. Agents propose, gates enforce, a human merges.

## You wrote it down, but…

Every team has the documents. Almost no team has a mechanism that
 notices when they stop being true.

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
      - uses: tarvitave/keelspec@v0.2.0
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

## Four agent critics, each trying to refute the work.

The agent that builds a change does not get to grade it. A separate
 station attacks the result through four independent lenses, on a different provider
 — so the critic cannot share the builder's blind spots. Diversity is a
 correctness lever, not a nicety.

### correctness

Find an input where it does the WRONG thing — and do the tests pass vacuously?

### coverage

Does every acceptance criterion map to a test that would catch its regression?

### security

Payments lens: authz, trust boundaries, injection, PII, secrets, spend / consent.

### reproduce

Ignore the happy path: concurrency, partial failure, retries / idempotency, rollback.

Provenance is not correctness. Knowing which agent wrote a line tells you nothing
 about whether the line is right — so **correctness is stacked on top, in
 depth**: an adversarial test station, four refuting lenses, then a deterministic
 gate, then a human.

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

## Extracted from a payments platform, not a demo.

KeelSpec is the product-as-code engine of the
 **pharthing / KibiPay** payments platform. It was pulled out of a
 working system so any team could use it.

pharthing's CI runs **keelspec validate** as its sole product gate,
 via a plugin that adds its domain-specific checks. A
 **byte-identical parity test** proves the extracted engine produces
 exactly the bundle the original in-house one did — nothing was lost on the way out.
 That's the plugin system, doing real work, in production.

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
