---
id: POST-the-staleness-gate
title: PAC-060, the check nobody else has
slug: the-staleness-gate
date: 2026-02-18
summary: Schema validation is common. Reference checking is rare. Proving the committed build still matches its sources is the one that catches real drift.
author: KeelSpec
category: reference
tags: [diagnostics, ci]
related: [POST-committing-generated-bundles, POST-ci-gate-anatomy]
reading_minutes: 4
---

KeelSpec emits seven core diagnostic codes. Six of them do what you would expect: required fields, id prefixes, filename agreement, duplicates, enum membership, reference resolution. Useful, unremarkable.

`PAC-060` is the one that earns its place.

## What it checks

The artifacts compile to a JSON bundle, and that bundle is committed to the repository. `PAC-060` recomputes the bundle from the current sources and compares it to the committed one. If they differ, the build fails:

```
PAC-060  build/product.generated.json is stale - run: keelspec build (and commit it)
```

That is it. It is almost embarrassingly simple, and it catches a class of failure that nothing else does.

## Why it matters

Consider what "stale" actually means here. Either:

- somebody edited an artifact and did not rebuild, so what you *ship* is older than what you *wrote*; or
- somebody edited the generated bundle directly, so what you wrote no longer explains what you ship.

Both are drift. Both are silent. Neither is visible in a normal code review, because in the first case the bundle is simply absent from the diff and in the second the source is.

`PAC-060` makes both impossible to merge.

## Determinism is the prerequisite

A staleness check is only usable if the build is byte-stable. If the compiler emits keys in hash order, or embeds a timestamp, the check fires constantly and the team learns to ignore it -- which is worse than not having it.

So the bundle is emitted with sorted keys, a fixed indent, and no timestamps. The same sources always produce the same bytes. That makes a diff on the bundle meaningful: every changed line corresponds to a real change in intent.

This is also why the parity test in the original payments extraction could be byte-identical. Determinism is not a nicety; it is what makes the whole gate trustworthy.

## Plugin outputs too

If a plugin emits extra outputs -- a runtime catalogue, a search index -- those are staleness-gated on exactly the same terms. A generated artifact that can silently fall behind is a generated artifact that will.

## The general principle

Most validation asks "is this document well-formed?" That is the easy question, and it is not where drift lives.

`PAC-060` asks a harder one: does the thing you are shipping still correspond to the thing you wrote? You can only ask that if both are in the repository and the compilation between them is reproducible.

Which is the argument for committing your build output, and the subject of another post.
