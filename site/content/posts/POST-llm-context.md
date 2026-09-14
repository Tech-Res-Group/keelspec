---
id: POST-llm-context
title: Feeding an LLM your product truth
slug: llm-context
date: 2026-05-06
summary: A validated bundle is the best context you can give a model, precisely because something guarantees it is current.
author: KeelSpec
category: practice
tags: [llm, context]
related: [POST-docs-from-bundles, POST-what-is-product-as-code]
reading_minutes: 4
---

Retrieval over a wiki has a failure mode nobody likes to name: the model faithfully retrieves a document that is two years out of date and answers with total confidence.

The retrieval worked. The index worked. The embedding worked. The content was wrong, and no part of the pipeline was responsible for noticing.

## Currency is a property of the source

You cannot fix stale context downstream. Reranking does not know what is true. A larger context window just includes more stale documents. Prompting the model to "only use current information" asks it to determine something it cannot possibly determine.

The only place currency can be established is at the source, before retrieval exists.

This is what a validated bundle gives you. Not that it is *correct* -- no tool can promise that -- but that it is *internally consistent and not stale relative to its sources*. Every reference resolves. Every enum is in range. The compiled artifact matches the markdown that produced it, because CI refuses to merge otherwise.

## The bundle is already the right shape

`product.generated.json` is structured, typed, and complete. That makes it far better raw material than scraped HTML:

- **Slice by type.** Answering a terminology question? Send the terms collection. You do not need a vector search to know that.
- **Traverse instead of guessing.** The graph is explicit, so pulling a rule and the features it applies to is a lookup, not a similarity gamble.
- **Cite precisely.** Every record has an id and a `_file`. Answers can point at `BR-idempotent` in a specific file, which a reader can verify.
- **Cache it.** The bundle changes on merges, not continuously. It is an ideal stable prefix for prompt caching.

## Small enough to skip retrieval

Most product models are smaller than people assume. A few hundred artifacts is a few hundred kilobytes -- comfortably inside a modern context window.

If the whole model fits, retrieval is a step you can delete. No index to rebuild, no staleness between the index and the source, no chunking artefacts. Send the collection, ask the question.

Retrieval is a compression strategy for context that does not fit. Check whether yours does not fit before building the machinery.

## The honest limitation

None of this makes a model correct. It removes one specific failure -- answering from a document that stopped being true -- and leaves every other failure exactly where it was.

That is still worth having, because it is the failure users find hardest to detect.
