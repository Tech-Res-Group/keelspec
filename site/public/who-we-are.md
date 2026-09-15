---
title: Who We Are — KeelSpec
description: The people behind KeelSpec and the payments platform it was extracted from.
url: https://keelspec.com/who-we-are.html
---
# Who we are

KeelSpec was not built as a product. It was built because a payments platform
needed its product intent to stop rotting, and the thing that fixed it turned out to be worth
extracting.

## Colin Wynd

Built the product-as-code engine inside the pharthing /
 KibiPay payments platform, where it grew to cover 39 features, a concept catalogue and a
 rulebook, and became the platform's sole product CI gate. Extracted it as KeelSpec so
 other teams could use it — verified by a byte-identical parity test proving nothing
 was lost on the way out.

Every design decision in the tool came from something going wrong first: the staleness
 gate because specs silently diverged from builds, typed references because renames quietly
 orphaned business rules, plugins because a real migration cannot afford to drop any of its
 bespoke checks.

He writes about software and other preoccupations at
 [tarvit.com](https://tarvit.com).

## Where it came from

The pharthing / KibiPay payments platform runs `keelspec validate` as its only
product gate, via a plugin that adds domain-specific checks. Every feature in the tool exists
because something went wrong without it: the staleness gate because specs silently diverged from
builds, typed references because renames quietly orphaned business rules, plugins because a real
migration cannot afford to lose any of its bespoke checks.

You can read more about what survived contact with production in
[what we learned running this in payments](/blog/payments-case-study.html).

## What we believe

- **Gates check facts, not taste.** A validator that argues about judgement gets
 bypassed, and a bypassed gate is worse than none.
- **Codes are an API.** Diagnostic numbers are never renumbered, because
 everything downstream depends on them.
- **Ship the smallest thing that closes the loop.** Most of the value is two
 checks: do references resolve, and does the build match its sources.

## Get in touch

Bugs and feature requests belong on
[GitHub](https://github.com/Tech-Res-Group/keelspec/issues), where they are public and
tracked. Anything else, use the [contact page](/contact.html).

[Back to the front page](/)
