# KeelSpec's own intent

The rules this library holds itself to, as a KeelSpec graph. Validated by
`keelspec` on every push — see the *"The engine's own intent must validate"* step
in [`ci.yml`](../.github/workflows/ci.yml).

```
product/
  decisions/KDR-*.md    the calls, immutable once accepted
  constraints/CON-*.md  boundaries this library does not get to move
  rules/BR-*.md         invariants that must always hold
  terms/TERM-*.md       the glossary
```

## Why this exists

Not to demonstrate the tool. Two trees in this repository already do that — the
[keelspec.com blog](../site/content) compiles its posts as typed artifacts, and
[`examples/quickstart`](../examples/quickstart) models a domain the engine knows
nothing about. Both are gated in CI.

This one is here because the engine's own policy was written down only in the
repositories that consume it. "Diagnostic codes are an API — retire, never
renumber" is a promise to *every* user of this library, and until now the only
places it was recorded were a consumer's decision record and a consumer's
`CLAUDE.md`. Somebody evaluating `pip install keelspec` could not read the rules
the validator holds itself to, which is precisely what a person wants to know
before letting a validator into their CI.

## Start here

- [`KDR-0001`](decisions/KDR-0001-the-engine-is-a-library-not-a-vendored-validator.md)
  — why this is a library and not a script each repository copies.
- [`CON-codes-are-an-api`](constraints/CON-codes-are-an-api.md) — the stability
  promise, and an honest note that nothing enforces it yet.
- [`CON-core-holds-no-consumer-vocabulary`](constraints/CON-core-holds-no-consumer-vocabulary.md)
  — the line that keeps the extraction meaningful.

## What is deliberately absent

**No features, and no roadmap.** A library's capabilities are all enablers with
no metric, no deployment and no synthetic probe. A features tree here would
restate [`CHANGELOG.md`](../CHANGELOG.md) in frontmatter and never reach a
meaningful `shipped`. Add one if a capability turns out to carry an invariant
worth stating — and then it is probably a rule.

**No plugin.** Core alone validates this tree: schema, ids, cross-references,
enums, staleness. That is the honest demonstration of how far core gets you
before you need one. Consumers reach for a plugin when they want a definition of
done; this tree does not have one to enforce.

## Adding to it

Write a decision when you make a real call about the engine — then don't edit it.
Supersede it with a new one and set `supersedes` on the new record, which is a
declared edge and must resolve.

Then regenerate the bundle and commit it:

```bash
keelspec build      # rewrites build/product.generated.json
keelspec validate   # 0 errors required
```

A stale bundle fails the gate (`PAC-060`).
