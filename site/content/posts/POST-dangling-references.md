---
id: POST-dangling-references
title: What a dangling reference actually costs
slug: dangling-references
date: 2026-03-04
summary: PAC-020 looks like a link checker. It is really a rename detector, and renames are where product knowledge goes to die.
author: KeelSpec
category: reference
tags: [diagnostics, graph]
related: [POST-the-staleness-gate, POST-naming-ids]
reading_minutes: 4
---

Somebody decides `TERM-payment` was always the wrong word and renames it to `TERM-charge`. One file changed. The pull request looks harmless.

Three other artifacts referenced the old id. Without a check, all three merge pointing at something that no longer exists.

## The failure is silent and slow

Nothing crashes. No test goes red. The rendered glossary shows a link that goes nowhere, or worse, silently omits it. A business rule now cites a concept that cannot be looked up.

Six months later someone reads that rule, cannot find the concept, and reconstructs what they think it meant. Now there are two meanings in circulation, and the team has a subtle and expensive disagreement that nobody can trace to its origin.

That is what a dangling reference costs. Not a broken link -- a fork in the shared model.

## PAC-020

```
PAC-020  product/rules/BR-idempotent.md: applies_to 'TERM-payment'
         does not resolve to a terms id
```

The check runs on every push. The rename above fails in seconds, with the three offending files named, before a reviewer has opened the PR. The author fixes them while the change is still in their head -- which is the only moment when fixing it is cheap.

## Why prose links cannot do this

You could write a markdown link and run a link checker. That catches a missing *file*. It does not catch:

- a file that exists but whose id changed
- a reference to a concept that was merged into another
- a reference that is structurally fine but points at the wrong collection
- a field that should reference a rule but points at a feature

Declared references carry the target *type*. `applies_to` must resolve to a `features` id, and pointing it at a term is an error even though a file exists. A link checker cannot express that, because prose links have no type.

## The compounding effect

The value grows superlinearly with the size of the graph. With twenty artifacts you could audit by hand. With three hundred, spread across a glossary, a rulebook, a feature catalogue and a decision log, nobody has the whole thing in their head -- and that is exactly when confident renames start doing damage.

A reference check turns the graph's size from a liability into an asset. The bigger it gets, the more the machine is doing for you.
