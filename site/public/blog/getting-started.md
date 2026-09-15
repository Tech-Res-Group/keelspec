---
title: Product-as-code in thirty minutes — KeelSpec
description: A working glossary, a rulebook, and a CI gate, starting from an empty directory.
url: https://keelspec.com/blog/getting-started.html
---
# Product-as-code in thirty minutes

A working glossary, a rulebook, and a CI gate, starting from an empty directory.

The fastest way to understand this is to run it. Thirty minutes, start to finish.

## Install

```
pip install keelspec
```

Or scaffold a complete repository -- config, example artifacts and the CI gate -- in one command:

```
pipx run copier copy --trust gh:Tech-Res-Group/keelspec my-product-repo
```

`--trust` lets the template run `keelspec build` once so the new repository is valid on its first commit.

## Declare two types

`product.config.yaml`:

```
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

```
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

```
keelspec build       # -> build/product.generated.json  (commit it)
keelspec validate    # schema + graph + staleness
```

`validate` exits non-zero when it finds errors. That exit code is the entire contract.

## Gate it

```
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

### Related

- [Migrating a wiki to product-as-code](/blog/migrating-a-wiki.html)
- [What product-as-code actually means](/blog/what-is-product-as-code.html)

## Get the next one by email.

Short notes on product-as-code,
 new diagnostic codes, and what breaks in real repositories. Twice a week, unsubscribe in one click.
