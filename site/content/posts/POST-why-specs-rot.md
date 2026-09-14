---
id: POST-why-specs-rot
title: Why specs rot, and why discipline will not fix it
slug: why-specs-rot
date: 2026-02-11
summary: Documentation decay is a structural problem, not a motivational one. Teams that resolve to try harder produce the same rot, slightly later.
author: KeelSpec
category: concept
tags: [drift, culture]
related: [POST-what-is-product-as-code, POST-the-staleness-gate]
reading_minutes: 4
---

Every team has had the meeting. The docs are out of date, everyone agrees it is bad, and the remedy proposed is that people should update them. Six months later the docs are out of date and the meeting happens again.

The remedy fails because it misdiagnoses the problem.

## Rot is asymmetric

Writing a document is a discrete act with a deadline attached. Keeping it true is a continuous obligation with no deadline at all. Those are not the same kind of work, and only one of them shows up in a sprint.

Worse, the cost of *not* updating is deferred and diffuse. The person who renames a concept in code pays nothing. The cost lands months later on someone else, usually someone new, who reads a confident sentence and believes it.

Any system where the cost of a mistake lands on a different person than the one making it will accumulate that mistake indefinitely. This is not a character flaw. It is an incentive structure.

## Prose hides its own dependencies

If a function changes signature, every caller breaks loudly. If a concept changes meaning, every document that assumed the old meaning stays syntactically perfect and semantically wrong.

Documents have dependencies -- on terms, on rules, on other documents -- but those dependencies are written in English, so no tool can see them. You cannot get a "who references this" list for a paragraph.

This is why the same team that maintains a rigorous type system tolerates a rotting glossary. They are not being inconsistent. Their tools simply cannot see one of the two.

## Review does not catch it

The reviewer of a pull request sees the diff. A stale document is not in the diff -- that is precisely what makes it stale. Asking reviewers to notice the absence of a change is asking them to hold the entire product model in their head on every review.

## What actually works

Move the structural claims out of prose and into something checkable, then check it on every change. Not because engineers need policing, but because the loop needs closing: the person making the change should find out immediately, while the context is still in their head.

That is the entire mechanism. A rename that breaks three references should fail the build in fourteen seconds, not surface in a support ticket next March.

Discipline is not the input. It is what you get to stop spending.
