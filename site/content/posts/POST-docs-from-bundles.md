---
id: POST-docs-from-bundles
title: Rendering docs sites from one bundle
slug: docs-from-bundles
date: 2026-06-03
summary: One compiled artifact, many surfaces. The point is not convenience -- it is that the surfaces cannot disagree.
author: KeelSpec
category: practice
tags: [docs, rendering]
related: [POST-llm-context, POST-committing-generated-bundles]
reading_minutes: 4
---

Most organisations have the same concept explained in four places: the public docs, the in-app help, an internal wiki, and a slide deck. All four were correct when written. At least two are wrong now.

The problem is not that there are four surfaces. Users legitimately need different depth in different contexts. The problem is four independent *sources*.

## One source, many renderers

Compile once, render many times. `product.generated.json` is the source; each surface is a rendering of it.

- The public docs site renders terms and features as pages
- The app renders definitions as tooltips from the same terms
- An internal catalogue renders the full graph with cross-links
- The LLM context is a slice of the same JSON

None of these hold their own copy. Change a definition, rebuild, and every surface updates on the next deploy.

## The blog you are reading

This site does it too. The posts are typed artifacts under `content/posts/`, with a `product.config.yaml` declaring their shape: ids must match filenames, `category` must be in the allowed set, and every `related` link must resolve to a real post.

`keelspec build` compiles them to `blog.generated.json`. A short renderer turns that into static HTML. If a post referenced a slug that did not exist, `PAC-020` would fail the build rather than shipping a dead link.

The blog is a demo of the product it describes, which is the only honest way to sell a tool like this.

## Rendering is boring on purpose

The renderer should be a template loop over a JSON file. If it is doing anything clever -- inferring structure, parsing prose, guessing relationships -- that logic belongs in a bundle transformer, computed once at build time and committed.

Consumers should not contain knowledge about the model. That is how the four-sources problem comes back in a new costume.

## What stays separate

Not everything should render from the bundle. Tutorials, narrative guides and onboarding material are prose whose value is the sequencing. Trying to generate them from artifacts produces something technically accurate and unreadable.

Generate the reference material. Write the guides. Link the guides to artifact ids so a validator can tell you when a guide references something that no longer exists.
