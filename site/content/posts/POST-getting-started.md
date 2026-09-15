---
id: POST-getting-started
title: Product-as-code in thirty minutes
slug: getting-started
date: 2026-06-17
summary: A working glossary, a rulebook, and a CI gate, starting from an empty directory.
author: KeelSpec
category: practice
tags: [tutorial, adoption]
related: [POST-migrating-a-wiki, POST-what-is-product-as-code]
reading_minutes: 5
---

The fastest way to understand this is to run it. Thirty minutes, start to finish.

## Install

```bash
pip install keelspec
```

Or scaffold a complete repository -- config, example artifacts and the CI gate -- in one command:

```bash
pipx run copier copy --trust gh:Tech-Res-Group/keelspec my-product-repo
```

`--trust` lets the template run `keelspec build` once so the new repository is valid on its first commit.

## Declare two types

`product.config.yaml`:

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
  - name: rules
    dir: rules
    id_prefix: "BR-"
    required: [id, title, statement]
    fields: [title, statement]
```

## Write an artifact

`product/terms/TERM-payment.md`:

```markdown
---
id: TERM-payment
term: Payment
definition: An instruction to move money between two parties.
see_also: [TERM-ledger]
---
The canonical unit of work in the system.
```

Note `see_also` points at `TERM-ledger`. Build now and it fails, because that term does not exist yet -- which is the tool working correctly. Write it, or drop the reference.

## Build and validate

```bash
keelspec build       # -> build/product.generated.json  (commit it)
keelspec validate    # schema + graph + staleness
```

`validate` exits non-zero when it finds errors. That exit code is the entire contract.

## Gate it

```yaml
name: product-as-code
on: [pull_request, push]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Tech-Res-Group/keelspec@v0.2.0
```

Commit the bundle alongside the artifacts. That is what makes staleness detectable.

## Now break it on purpose

Worth five minutes: rename `TERM-ledger` and push. Watch `PAC-020` name the file that still references the old id. Delete a required field and watch `PAC-001`. Edit the committed bundle by hand and watch `PAC-060`.

Seeing the failures is what makes the value concrete. Everything after this is adding collections and, eventually, a plugin.
