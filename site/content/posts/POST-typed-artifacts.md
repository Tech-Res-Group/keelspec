---
id: POST-typed-artifacts
title: Why typed artifacts beat free-form documents
slug: typed-artifacts
date: 2026-02-25
summary: The moment a document has a declared shape, a whole class of question becomes machine-answerable.
author: KeelSpec
category: concept
tags: [schema, modelling]
related: [POST-what-is-product-as-code, POST-naming-ids]
reading_minutes: 4
---

A free-form document can say anything, which sounds like freedom and behaves like debt.

Give the same content a declared shape -- an id, a set of required fields, an allowed set of values, some typed references -- and questions that were previously research tasks become one-line queries.

## Questions you can suddenly answer

- Which business rules have no feature implementing them?
- Which terms are defined but referenced nowhere?
- Which features claim a status that is not in our lifecycle?
- What breaks if we rename this concept?
- How many artifacts changed in this release, and which?

None of these are exotic. Every one is unanswerable against a folder of prose, and trivial against a typed graph. Not because the prose lacks the information, but because extracting it requires a human to read everything.

## The shape is yours

The important design decision in KeelSpec is that it ships no schema. You declare your collections in `product.config.yaml`:

```yaml
types:
  - name: rules
    dir: rules
    id_prefix: "BR-"
    required: [id, title, statement]
    fields: [title, statement, applies_to]
    references:
      - field: applies_to
        to: features
```

A generic schema would be wrong for everyone. Your domain has concepts that no tool vendor has heard of, and the ones it does ship -- "epic", "story" -- usually encode a methodology you did not choose.

## Types are a conversation, not a cage

In practice the schema evolves, and that is healthy. You start with terms and rules. Someone adds features and wants them to reference rules. Later a lifecycle appears and `status` gets an enum. Each tightening is a small pull request, and the validator immediately tells you which existing artifacts violate the new constraint.

That last part is the quiet benefit. Tightening a schema on a folder of prose is a manual audit. Tightening it on typed artifacts is a build failure with a file list.

## Keep the prose

None of this removes writing. Every artifact has a body below the frontmatter, and the body is where reasoning, nuance, examples and caveats live. Structure the claims that machines can check; leave the thinking in English.

The split is the point: the frontmatter is a contract, the body is a conversation. Enforce the contract, and the conversation gets better because nobody is using it to store facts that should have been fields.
