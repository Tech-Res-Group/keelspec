---
title: What we learned running this in payments — KeelSpec
description: KeelSpec was extracted from a payments platform running 39 features and a 283 KB bundle. Here is what survived contact with production.
url: https://keelspec.com/blog/payments-case-study.html
---
# What we learned running this in payments

KeelSpec was extracted from a payments platform running 39 features and a 283 KB bundle. Here is what survived contact with production.

KeelSpec did not begin as a tool. It began as the product-as-code engine inside the pharthing / KibiPay payments platform, and it was extracted so other teams could use it. That order matters: every feature exists because something went wrong without it.

## The numbers

39 features under the gate, a concept catalogue, a rulebook, and a compiled render bundle of about 283 KB. `keelspec validate` is the sole product gate in CI, running through a plugin that adds domain-specific checks.

The extraction was verified by a **byte-identical parity test**: the extracted engine produces exactly the bundle the in-house one did. Not equivalent -- identical. That test is the reason the extraction could be trusted, and it is only possible because the build is deterministic.

## What earned its place

**The staleness gate.** In a domain where a business rule is the difference between a correct ledger and an incident, a spec that has silently diverged from the build is a real risk. `PAC-060` fires more often than any other code during normal work, almost always because someone edited an artifact and forgot to rebuild. Fourteen seconds of CI, every time.

**Typed references.** The concept graph in payments is dense -- settlement references clearing references reconciliation. Renames happen, because the domain vocabulary genuinely improves as the team learns it. Every rename is mechanical because `PAC-020` produces the exact list of what to update.

**Plugins.** The platform's own checks -- that a feature's claimed code paths exist, that reverse edges are computed for the renderer, that a runtime catalogue is emitted -- are all plugin hooks. None of them are in the core tool, and none of them required forking it. This is the mechanism that let a large existing project adopt the extracted engine without losing anything.

## What we got wrong first

**Too much schema, too early.** The first version had required fields nobody could reliably supply, so artifacts accumulated placeholder values. Placeholder values are worse than missing ones: they look like data. The fix was to require less and add constraints only once the content proved they held.

**Checks that needed judgement.** An early validator flagged definitions under a certain length. It was wrong often enough that people started reaching for the bypass, which briefly put the whole gate at risk. It was deleted. Gates check facts.

**Ids encoding structure.** Early ids embedded team and grouping. Both changed within a year. Now ids are flat and semantic, and the changeable parts are fields.

## The honest summary

The tool is small because the useful part is small. Most of the value is in two checks -- do references resolve, and does the build match its sources -- run automatically on every change. Everything else is ergonomics around those two questions.

### Related

- [Extending the validator with plugins](/blog/plugins-deep-dive.html)
- [PAC-060, the check nobody else has](/blog/the-staleness-gate.html)

## Get the next one by email.

Short notes on product-as-code,
 new diagnostic codes, and what breaks in real repositories. Twice a week, unsubscribe in one click.
