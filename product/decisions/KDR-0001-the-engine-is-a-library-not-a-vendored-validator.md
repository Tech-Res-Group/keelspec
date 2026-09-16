---
id: KDR-0001
title: The engine is a library, not a vendored validator
status: accepted
date: 2026-08-22
---
## Context

Product-as-code started inside a payments platform as a validator script living
in the repository it validated. That works exactly once. The second repository to
want it copied the script, and the two copies immediately began to differ —
because each copy was edited to suit the tree in front of it, and nobody could
tell which differences were deliberate.

A validator that lives inside one product acquires that product's vocabulary. The
payments version knew what a ledger was. Anything it learned about ledgers was
then in the way of the next consumer, and anything the next consumer needed had
to be added to a file that the payments repository also had to carry.

## Decision

Extract the engine as an installable library with no knowledge of any consumer's
domain. A consumer declares its artifact types in `product.config.yaml` and adds
its own rules as a plugin. The library does loading, schema, ids,
cross-references, enums and bundle staleness, and nothing else.

Consumers pin an exact version. The library is not a framework: it does not own
the consumer's directory layout, its CI, or its definition of done.

## Consequences

Two repositories that were forks of one script became two consumers of one
package with their own plugins — KibiPay (`../pharthing`, PDR-0005 and PDR-0008
there) and FifeRouter (PDR-0003, 2026-08-23, which also records the single
diagnostic-code renumbering the move forced).

The cost is that a rule which genuinely belongs to the engine can no longer be
written where it is enforced without either putting it in every consumer or
putting it here. For a year it went in the consumers, which is the gap this tree
exists to close.

The constraint that keeps the extraction meaningful is
[`CON-core-holds-no-consumer-vocabulary`](../constraints/CON-core-holds-no-consumer-vocabulary.md).
Without it, this decision decays into a shared script with a `pip install` in
front of it.
