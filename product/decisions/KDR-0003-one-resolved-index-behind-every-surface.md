---
id: KDR-0003
title: One resolved index behind every surface
status: accepted
date: 2026-09-14
---
## Context

The engine grew from one surface to four: the CLI, a language server, an MCP
server, and a watch mode. All four answer the same questions — what artifacts
exist, what does this id refer to, which edges point here, where in the file is
that — and each one was in a position to answer them its own way.

That is the shape that produces a tool people stop trusting. An editor reporting
a dangling reference the CLI accepts is not a cosmetic inconsistency; it makes
both answers worthless, because the user has no way to tell which surface is
wrong.

The first shared index was keyed by bare artifact id, which looked correct and
was not. In a tree where a spec and the feature it details deliberately share an
id, every such pair collapsed into one entry: 85 artifacts resolved to 62. The
CLI, which did its own loading, disagreed — correctly — and the disagreement was
the only reason it was found.

## Decision

Every surface resolves through one index, and the index is keyed by
`(type_name, id)` rather than by id alone. Edges are typed on both ends: an edge
records the source type, source id, field, target type and target id.

A surface may present differently — a diagnostic, a hover, a JSON payload, a
terminal line — but it may not answer a question about the graph from its own
traversal.

## Consequences

Looking an artifact up by bare id becomes an operation that returns a list, not
an artifact, because the id alone does not identify one. Callers that want a
single artifact must say which type they mean. That is more awkward and it is
correct: the awkwardness is the ambiguity, made visible.

Adding a fifth surface is now mostly presentation, which is the payoff.

The invariant is stated as
[`BR-one-index-behind-every-surface`](../rules/BR-one-index-behind-every-surface.md).
The failure it prevents is silent, so it is worth restating that nothing about
the collapsed index looked broken — the count was simply lower than it should
have been, on a number nobody had a reason to check.
