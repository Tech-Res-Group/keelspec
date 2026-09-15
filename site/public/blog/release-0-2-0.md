---
title: KeelSpec 0.2.0 — evidence records and the agent-built lifecycle — KeelSpec
description: Two new surfaces on top of the compiler and the gate. The core is unchanged - two dependencies, no network, still the thing CI runs.
url: https://keelspec.com/blog/release-0-2-0.html
---
# KeelSpec 0.2.0 — evidence records and the agent-built lifecycle

Two new surfaces on top of the compiler and the gate. The core is unchanged - two dependencies, no network, still the thing CI runs.

`pip install keelspec` now gets you 0.2.0. `build` and `validate` are untouched: same two dependencies, same absence of network access, same job. Everything below is additive.

## The agent-built lifecycle

```
pip install 'keelspec[agents]'
keelspec orchestrate FEAT-refunds
```

A station line runs over one artifact: **Understand → Disambiguate → Design → Develop → Test → adversarial Verify**, with a bounded repair loop.

Control flow is ordinary code and reasoning happens inside a station. That split is the whole design: a pipeline where steps depend on each other, fan-out where they do not, and a barrier only for synthesis. Nothing about the wiring is left to a model to remember.

### Four critics, each trying to refute

Verify runs four lenses in parallel — **correctness, coverage, security, reproduce** — each defaulting to *refuted* unless convinced. The agent that built the change never grades it.

`--cross-provider` adds a fifth verdict from a non-Claude model. A critic drawn from the builder's own family can share its blind spots, which is exactly the failure mode adversarial review is supposed to catch. Without `OPENROUTER_API_KEY` the lens is skipped and the run is identical to native-only; if the call fails it abstains rather than blocking. One unreachable critic must never become an outage.

Minor findings deliberately do not block. A gate that fires on nitpicks trains people to bypass it, and a bypassed gate is worse than none.

### The human gate blocks

Plain-English acceptance criteria hide enormous ambiguity. "Refund window: 30 days" says nothing about whether the clock starts at authorization, settlement or delivery — nor about partial refunds, chargebacks, or what happens when the ledger write fails.

So Disambiguate runs *before* Design and stops the line. Building the wrong thing correctly is the expensive failure.

A blocking human gate cannot live inside one autonomous run, so it is two-phase by construction. Run one writes the open questions and exits:

```
{
  "status": "pending",
  "questions": [
    { "id": "q1", "dimension": "refund window start",
      "question": "From authorization, settlement or delivery?", "answer": "" }
  ]
}
```

A person fills in each `answer`. Run two reads them and proceeds.

### Writing code

Develop is the only station that needs tools, so it runs a bounded loop with three: list, read, write. Confined to the project root, with containment checked *after* path resolution — so `..`, absolute paths and symlink escapes are refused rather than sanitised. No shell, no network, no delete, no rename.

`--write` is opt-in. By default the station proposes a diff and touches nothing, because the thing holding those tools is a model. Run it on a clean branch.

### What the line cannot do

It cannot merge. The terminal state is a report; every station past the gate is deterministic or human by construction, and a test asserts it. It also cannot run tests — Develop has no shell — so a passing test report is a *claim* your CI still has to check. That split is arguably correct, but it should be stated rather than discovered.

## Evidence records

```
keelspec evidence -o build/evidence.json
```

What was checked, when, on which commit, with what result. Every artifact, the config and the bundle carry a SHA-256, so the record is verified by recomputing digests rather than by trusting whoever produced it — a stronger property than a signature here, since a signature proves who made a claim and a digest proves the claim is true.

There is deliberately no `--since`. Historical evidence is a checkout away: bundles are byte-stable, so `git checkout <sha> && keelspec evidence` reproduces the same digests. Walking history inside the tool would only have hidden the property that makes the whole thing work.

## One fix worth naming

YAML parses an unquoted `date: 2026-02-04` into a `datetime.date`, which `json.dumps` cannot serialize. Any project with a date field hit this. Bundles now emit ISO-8601 strings.

It was found by using the tool on this blog, which is itself a product-as-code collection — ids matching filenames, categories from an allowed set, every `related` link resolving. The post you are reading had to pass the gate to exist.

### Related

- [PAC-060, the check nobody else has](/blog/the-staleness-gate.html)
- [Extending the validator with plugins](/blog/plugins-deep-dive.html)

## Get the next one by email.

Short notes on product-as-code,
 new diagnostic codes, and what breaks in real repositories. Twice a week, unsubscribe in one click.
