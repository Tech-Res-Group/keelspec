---
title: Blog — KeelSpec
description: Notes on product-as-code: why specs rot, what a validated graph buys you, and what breaks in real repositories.
url: https://keelspec.com/blog/
---
# Notes on product-as-code.

Why specs rot, what a validated graph buys you, and what breaks in real
 repositories. Every post on this page is a typed artifact — ids, categories and
 cross-links are validated by `keelspec` in CI.

### KeelSpec 0.2.0 — evidence records and the agent-built lifecycle

Two new surfaces on top of the compiler and the gate. The core is unchanged - two dependencies, no network, still the thing CI runs.

### Product-as-code in thirty minutes

A working glossary, a rulebook, and a CI gate, starting from an empty directory.

### Finding the artifacts nobody references

A graph makes absence visible. Orphans are usually either dead weight or a missing link, and both are worth knowing about.

### Rendering docs sites from one bundle

One compiled artifact, many surfaces. The point is not convenience -- it is that the surfaces cannot disagree.

### What we learned running this in payments

KeelSpec was extracted from a payments platform running 39 features and a 283 KB bundle. Here is what survived contact with production.

### Modelling lifecycles with enums

Four spellings of in-progress is not a naming problem. It is a missing constraint, and PAC-030 is the fix.

### Reviewing product changes in pull requests

When intent lives in the repository, product decisions get the same review rigour as code. That changes the conversation more than the tooling does.

### Feeding an LLM your product truth

A validated bundle is the best context you can give a model, precisely because something guarantees it is current.

### Extending the validator with plugins

Validators, bundle transformers, extra outputs and custom codes -- the four hooks, and when to reach for each.

### Migrating a wiki to product-as-code

How to move years of accumulated pages without a six-month project or a big-bang rewrite.

### ADRs, RFCs and where product-as-code fits

Decision records answer why. Product-as-code answers what is true now. Conflating them is why both rot.

### Naming artifact ids you will not regret

Ids are the most permanent thing you will write. A few conventions keep them from becoming a source of churn.

### Writing business rules that survive contact with code

A rule that cannot be violated by a specific line of code is not a rule. It is a sentiment.

### Commit the generated bundle

Build artifacts usually do not belong in git. This one does, and the reason is that it turns invisible drift into a reviewable diff.

### Diagnostic codes are an API

Treat your error codes with the same seriousness as your function signatures, because downstream systems depend on both.

### Anatomy of a product CI gate

What a good product gate checks, what it must never do, and why its exit code is the entire contract.

### What a dangling reference actually costs

PAC-020 looks like a link checker. It is really a rename detector, and renames are where product knowledge goes to die.

### Why typed artifacts beat free-form documents

The moment a document has a declared shape, a whole class of question becomes machine-answerable.

### PAC-060, the check nobody else has

Schema validation is common. Reference checking is rare. Proving the committed build still matches its sources is the one that catches real drift.

### Why specs rot, and why discipline will not fix it

Documentation decay is a structural problem, not a motivational one. Teams that resolve to try harder produce the same rot, slightly later.

### What product-as-code actually means

Not docs in a repo. Typed artifacts with a schema, a reference graph, and a build that fails when they stop being true.

## Get the next one by email.

Short notes on product-as-code,
 new diagnostic codes, and what breaks in real repositories. Twice a week, unsubscribe in one click.
