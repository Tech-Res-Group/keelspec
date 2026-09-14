---
id: POST-migrating-a-wiki
title: Migrating a wiki to product-as-code
slug: migrating-a-wiki
date: 2026-04-22
summary: How to move years of accumulated pages without a six-month project or a big-bang rewrite.
author: KeelSpec
category: practice
tags: [migration, adoption]
related: [POST-getting-started, POST-plugins-deep-dive]
reading_minutes: 5
---

The instinct is to model everything first. Resist it. Every large migration that starts with a complete schema stalls, because the schema is wrong in ways you cannot discover without content in it.

Start with one collection and one check.

## Step one: the glossary, nothing else

Pick the glossary. It is the smallest collection, the one with the clearest shape, and the one whose rot causes the most confusion.

```yaml
product_dir: product
output: build/product.generated.json
types:
  - name: terms
    dir: terms
    id_prefix: "TERM-"
    required: [id, term, definition]
    fields: [term, definition, see_also]
    references:
      - field: see_also
        to: terms
```

Move the terms. Do not improve them yet -- copy them across as they are. Improving and migrating at the same time makes it impossible to tell which change broke what, and it triples the review burden.

## Step two: turn on the gate before you feel ready

Add `keelspec validate` to CI while the glossary is still incomplete. The gate does not care that you have twelve terms instead of two hundred. What it does is stop the twelve from rotting while you migrate the rest.

Teams that wait until the migration is complete before enabling the gate spend the whole migration re-fixing things.

## Step three: let the failures design your schema

Now migrate a second collection and let the validator argue with you. You will discover that half your "rules" are decisions, that `status` needs an enum because four spellings of "in progress" exist, and that two terms have the same name in different contexts.

Every one of those is a modelling discovery you could not have made on a whiteboard. This is why the incremental order matters.

## Step four: bespoke checks become plugins

Eventually you will want something the config cannot express -- that a feature's `code` path exists on disk, that no rule is orphaned, that every term appears in at least one feature. Write a plugin, register codes in your own `9xx` range, and the checks join the same report.

This is the step that lets a large legacy project migrate with **no loss of functionality**, because whatever your old homegrown script checked, a plugin can check too.

## What to leave behind

Not everything belongs. Meeting notes, retrospectives, onboarding guides, runbooks -- these are prose with no structural claims, and forcing them into artifacts adds ceremony without adding checks.

Migrate what other things depend on. Leave what only humans read.
