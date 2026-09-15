---
id: POST-ci-gate-anatomy
title: Anatomy of a product CI gate
slug: ci-gate-anatomy
date: 2026-03-11
summary: What a good product gate checks, what it must never do, and why its exit code is the entire contract.
author: KeelSpec
category: practice
tags: [ci, workflow]
related: [POST-the-staleness-gate, POST-review-culture]
reading_minutes: 4
---

A gate is a program whose exit code decides whether a pull request can merge. That is the whole interface. Everything else -- the output format, the codes, the pretty printing -- is ergonomics layered on top of one bit.

Getting that bit right is mostly about restraint.

## What it should check

**Structural claims only.** Required fields present. Ids well-formed and unique. Enum values in range. References resolving. The committed build matching its sources.

Every one of those is objectively true or false. A machine can decide it without judgement, and a human reading the failure will agree immediately.

## What it must never check

**Anything requiring taste.** Whether a definition is *good*, whether a rule is *wise*, whether a feature *should* exist. Those are review conversations, and a gate that tries to have them will be wrong often enough that people start looking for the bypass flag.

The moment a team routinely skips your gate, you have less than nothing: you have a false sense of coverage.

## Fast, or it will be worked around

A product gate should finish in seconds. It reads some markdown, builds a dict, and compares strings. There is no excuse for it to take a minute. If it is slow, people push and context-switch, and the feedback arrives after they have moved on -- which destroys most of the value.

## Stable codes, not stable prose

Findings carry codes like `PAC-020`. The code is the API; the message is for humans and may be reworded any time. This matters because CI configuration, dashboards and team conventions all end up matching on *something*, and if the only stable thing is prose, every wording improvement breaks somebody's grep.

Never renumber a code. Retire it and add a new one.

## One command

```yaml
- uses: actions/checkout@v4
- uses: Tech-Res-Group/keelspec@v0.2.0
```

The gate should be a single step with no bespoke scripting around it. Every line of glue in a workflow file is a line that rots, and a gate that requires maintenance is a gate that gets deleted during the next CI cleanup.

## Failing well

A good failure names the code, the file, and the specific value that is wrong. A reader should be able to fix it without opening the tool's documentation:

```
ERROR PAC-030 product/features/FEAT-refunds.md: status 'in-progres'
      not in ['done', 'in-progress']
```

That message contains the typo, the file, and the allowed set. Nobody needs to look anything up. That is the standard.
