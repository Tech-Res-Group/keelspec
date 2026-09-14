---
id: POST-diagnostic-codes-as-api
title: Diagnostic codes are an API
slug: diagnostic-codes-as-api
date: 2026-03-18
summary: Treat your error codes with the same seriousness as your function signatures, because downstream systems depend on both.
author: KeelSpec
category: reference
tags: [diagnostics, design]
related: [POST-ci-gate-anatomy, POST-plugins-deep-dive]
reading_minutes: 3
---

Compilers learned this decades ago. `error: C2065` means something specific, forever, and an entire ecosystem of tooling depends on it.

Validation tools usually do not learn it, and then wonder why nobody automates around them.

## The contract

KeelSpec's core codes occupy documented ranges:

- `00x` required-field and schema
- `01x` id and graph integrity
- `02x` cross-reference resolution
- `03x` enum and allowed values
- `06x` generated-bundle staleness

The rule is short: **never renumber an existing code.** If a check changes meaning, retire the old number and add a new one. Renumbering silently breaks everything downstream, and it breaks it quietly, which is the worst way.

## What depends on codes

Once codes are stable, useful things become possible:

- CI suppresses a specific class of finding during a migration, without disabling the gate wholesale
- A dashboard tracks `PAC-020` count over time as a health metric
- A pre-commit hook fails on `PAC-06x` only, because staleness is the cheap local check
- A team convention says "`PAC-030` findings block release; warnings do not"

Every one of those is grep on a stable token. None of them survive prose changes.

## Your own range

Projects register their own codes through the plugin system, conventionally in a `9xx` range so they never collide with the core set:

```python
register("PAC-900", "links.code path does not exist on disk")
```

Now your bespoke check is a first-class citizen. It appears in the same report, matches the same patterns, and your dashboard does not care that it came from a plugin.

## Severity is part of the contract too

A finding is an error or a warning, and that classification is as much a promise as the number. Quietly promoting a warning to an error will break someone's build on a Tuesday morning for reasons they cannot see in their own diff. If a check needs to get stricter, that is a new code, or a major version, or an announcement -- ideally all three.

Stability is unglamorous. It is also the entire reason anyone will build on top of your tool.
