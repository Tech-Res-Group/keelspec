---
title: Writing business rules that survive contact with code — KeelSpec
description: A rule that cannot be violated by a specific line of code is not a rule. It is a sentiment.
url: https://keelspec.com/blog/business-rules.html
---
# Writing business rules that survive contact with code

A rule that cannot be violated by a specific line of code is not a rule. It is a sentiment.

Most documents labelled "business rules" contain a mixture of three things: actual invariants, product decisions, and encouragement. Only the first kind is worth the ceremony of an id.

## The test

A business rule should be falsifiable by pointing at code. If you cannot imagine the specific commit that violates it, it is not a rule.

**Not a rule:** "Payments should be reliable." Nothing violates this. Nothing can.

**A rule:** "A payment instruction with the same idempotency key must never be executed twice." You can point at the code that would break this. You can write a test for it. You can name the incident that happens when it fails.

The second one earns `BR-idempotent`. The first belongs in a strategy document where it will do less harm.

## Statement first, discussion after

Give each rule a `statement` field that is one sentence, present tense, and unconditional. That sentence is the contract; everything else is context.

```
---
id: BR-idempotent
title: Idempotent execution
statement: A payment instruction with a given idempotency key executes at most once.
applies_to: [FEAT-payments, FEAT-retries]
---

Retries are inevitable -- clients time out, networks partition, and queues redeliver.
Without this guarantee, every one of those becomes a double charge...
```

The discipline of one sentence is doing real work. If you cannot state the rule in one sentence, you usually have two rules, or you have a decision rather than an invariant.

## Reference the features that carry them

`applies_to` turns the rulebook into a graph. Now you can ask which features are load-bearing for a given invariant, and -- more usefully -- which rules a feature must not break. When someone proposes deleting a feature, the rules pointing at it are the blast radius.

And because the reference is checked, deleting a feature while a rule still cites it fails the build.

## Rules outlive features

Features get replaced; the invariants they served usually do not. Keeping rules in their own collection with their own ids means the invariant survives three rewrites of the thing that implements it. That is the whole reason to separate them.

A rule that changes every quarter was a design note. Move it.

### Related

- [Why typed artifacts beat free-form documents](/blog/typed-artifacts.html)
- [Modelling lifecycles with enums](/blog/enums-and-lifecycles.html)

## Get the next one by email.

Short notes on product-as-code,
 new diagnostic codes, and what breaks in real repositories. Twice a week, unsubscribe in one click.
