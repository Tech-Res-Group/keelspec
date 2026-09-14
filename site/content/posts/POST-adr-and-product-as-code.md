---
id: POST-adr-and-product-as-code
title: ADRs, RFCs and where product-as-code fits
slug: adr-and-product-as-code
date: 2026-04-15
summary: Decision records answer why. Product-as-code answers what is true now. Conflating them is why both rot.
author: KeelSpec
category: concept
tags: [decisions, modelling]
related: [POST-business-rules, POST-what-is-product-as-code]
reading_minutes: 4
---

Architecture decision records are one of the few documentation practices that reliably survives. They work because they are append-only: a decision is made, recorded, and never edited. Superseding one means writing a new record, not rewriting the old.

That immutability is exactly why ADRs cannot carry your current product model.

## Two different questions

An ADR answers **why did we choose this, and what did we know at the time**. Its value is historical. Reading a three-year-old ADR and finding it out of date is not a defect -- the decision really was made under those conditions.

A glossary answers **what does this word mean right now**. A rulebook answers **what invariants hold right now**. These must be current or they are actively harmful. There is no value in a glossary that documents what a term used to mean.

Teams get into trouble by storing the second kind of content in the first kind of document. The ADR says "we will call this a Payment", the name changes two years later, and the ADR is both correct as history and wrong as reference.

## Keep both, wired together

Model decisions as their own collection, with their own lifecycle:

```yaml
- name: decisions
  dir: decisions
  id_prefix: "ADR-"
  required: [id, title, status, date]
  fields: [title, status, date, supersedes, affects]
  enums:
    status: [proposed, accepted, superseded]
  references:
    - field: supersedes
      to: decisions
    - field: affects
      to: rules
```

Now `supersedes` is checked, so an ADR cannot claim to replace one that does not exist. `affects` links the decision to the invariants it changed, which is the query people actually want: *why is this rule the way it is?*

## The division of labour

- **Decisions** are immutable and dated. Never edit them; supersede them.
- **Terms and rules** are current and edited freely. Their history lives in git.

Both are typed artifacts in the same graph, and the references between them are validated. What you get is a current model you can trust, with a traceable path back to the reasoning -- without either document pretending to be the other.
