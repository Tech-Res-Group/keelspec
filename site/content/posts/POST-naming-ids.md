---
id: POST-naming-ids
title: Naming artifact ids you will not regret
slug: naming-ids
date: 2026-04-08
summary: Ids are the most permanent thing you will write. A few conventions keep them from becoming a source of churn.
author: KeelSpec
category: practice
tags: [modelling, conventions]
related: [POST-dangling-references, POST-typed-artifacts]
reading_minutes: 3
---

An id is a promise that other artifacts can depend on. Renaming one is a graph-wide operation. It is worth ten minutes of thought up front.

## Prefix by collection

`TERM-`, `BR-`, `FEAT-`, `ADR-`. KeelSpec enforces this with `id_prefix`, and the value is not bureaucratic: a bare id in a reference field tells a reader nothing, while `BR-idempotent` announces its collection. When you see it in a diff, in a log line, or in a support conversation, you know what kind of thing it is.

## Match the filename

The default is that `TERM-payment` lives in `TERM-payment.md`, and `PAC-011` enforces it. This sounds fussy until the first time you go looking for an artifact by id and find it instantly, or grep the repository for a reference and get both the definition and every citation in one result.

## Name the concept, not the wording

`TERM-payment` is good. `TERM-a-payment-is-an-instruction-to-move-money` is not, because the definition will be reworded and the id will not.

The id should survive rewrites of the artifact it names. Ask: if we completely rewrote this definition, would the id still be right? If not, it is describing prose rather than a concept.

## Avoid encoding hierarchy or ownership

`FEAT-payments-team-refunds-v2` bakes three things into a permanent string: a team, a grouping, and a version. All three will change. Teams reorganise, groupings get rethought, and v2 becomes v3.

Put those in fields, where they can change without a graph-wide rename. Ids should be flat and semantic.

## Do not number them

`BR-001` tells a reader nothing and makes the whole set impossible to reason about. It also creates a fake ordering, which invites questions about why `BR-014` comes before `BR-015` when nobody intended a sequence.

Use words. Ids are read far more often than they are typed.

## Renaming, when you must

Sometimes a concept genuinely changes name. The mechanics are the good news: change the id, change the filename, run the build, and let `PAC-020` list every artifact that needs updating. The rename is mechanical and complete, which is exactly the property free-form documents never had.
