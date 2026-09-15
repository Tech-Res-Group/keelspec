---
title: What product-as-code actually means — KeelSpec
description: Not docs in a repo. Typed artifacts with a schema, a reference graph, and a build that fails when they stop being true.
url: https://keelspec.com/blog/what-is-product-as-code.html
---
# What product-as-code actually means

Not docs in a repo. Typed artifacts with a schema, a reference graph, and a build that fails when they stop being true.

Most teams that say they do "docs as code" mean they moved their markdown into git. That is a storage decision, and storage was never the problem. The problem is that nothing checks the documents against reality, so they drift, and drift is invisible until someone acts on a stale sentence.

Product-as-code is a stronger claim: your product intent is a **typed, validated graph** that participates in your build.

Three properties make it real.

## It is typed

A glossary term is not a paragraph. It is a record with an id, a term, a definition, and optionally a list of related terms. Declaring that shape means a term missing its definition is a build error, not something a reader discovers eighteen months later.

You declare your own types. There is no universal schema for product intent, and any tool that ships one is wrong about your domain. Terms, business rules, features, decisions, personas, risks, invariants -- you name the collections and the fields.

## It is a graph

Artifacts reference each other. A feature implements a rule. A term relates to another term. A decision supersedes an earlier decision.

Once those references are declared rather than written as prose, they can be *checked*. Rename a term and every artifact pointing at the old id becomes a build failure with a filename attached. This is the single highest-value property of the whole approach, and it is impossible with free-form documents, because prose links are invisible to machines.

## It compiles, and the compilation is gated

The artifacts compile to one JSON bundle. Your docs site renders from it. Your app's in-product glossary renders from it. The context you hand an LLM comes from it. Because there is exactly one compiled artifact, those surfaces cannot disagree.

And the bundle is committed, which is the part people find odd until they see why: if the bundle only exists inside CI, nothing can prove that what you ship matches what you wrote. Committing it turns invisible drift into a visible diff on a pull request.

## What this is not

It is not a replacement for your wiki, your PRD template, or your product manager. Prose still matters -- every artifact has a body, and that body is where the thinking lives. What changes is that the *structural* claims get enforced while the prose stays free.

It is also not a process. Nobody has to adopt a methodology. You add a config file, write some markdown with frontmatter, and put one command in CI. If it fails, something is genuinely inconsistent.

That is the whole idea. The rest is detail.

### Related

- [Why specs rot, and why discipline will not fix it](/blog/why-specs-rot.html)
- [Why typed artifacts beat free-form documents](/blog/typed-artifacts.html)

## Get the next one by email.

Short notes on product-as-code,
 new diagnostic codes, and what breaks in real repositories. Twice a week, unsubscribe in one click.
