---
id: KDR-0002
title: Diagnostic codes are an API
status: accepted
date: 2026-09-14
---
## Context

Every diagnostic this library emits carries a code: `PAC-001` for a missing
required field, `PAC-020` for a reference that does not resolve, `PAC-060` for a
stale committed bundle. Codes are what consumers actually build on. They appear
in CI allowlists, in triage rules, in dashboards, in the messages people paste to
each other, and in the plugin ranges consumers register their own rules into.

A code is therefore not an internal label. Renumbering one is a breaking change
that produces no error anywhere: an allowlist keyed on the old number silently
stops matching, and a gate that was suppressing one class of warning starts
suppressing a different one. The failure is invisible at the moment it happens
and surfaces later as a rule that was supposed to be enforced and was not.

The library has renumbered exactly once, when consumers moved off their vendored
validators and the two numbering schemes had to be reconciled. FifeRouter's
PDR-0003 records that from the consumer side, including why it was accepted and
why it must not recur.

## Decision

A code, once released, keeps its meaning permanently. To retire a rule, stop
emitting the code and leave the number burned. Never reassign it, never
renumber a neighbouring code to close a gap, and never change what an existing
code means.

The ranges are fixed: `PAC-0xx` through `PAC-06x` belong to the engine, and
consumers register their own rules from `PAC-9xx`. A consumer must be able to add
a rule without asking whether the next engine release will collide with it.

## Consequences

The numbering will develop gaps, and the gaps are the point — a missing number is
a retired rule, which is information rather than untidiness.

New engine rules take the next free number in the engine's range. When the engine
range fills, the answer is a new range, not a compaction of the old one.

This is the rule most likely to be broken by a well-intentioned tidy-up, which is
why it is written down here rather than only in the consumer repository that
happened to pay for it once. It is stated as
[`CON-codes-are-an-api`](../constraints/CON-codes-are-an-api.md).
