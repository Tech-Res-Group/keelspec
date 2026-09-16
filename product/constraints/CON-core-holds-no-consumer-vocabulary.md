---
id: CON-core-holds-no-consumer-vocabulary
title: The engine holds the discipline, never the vocabulary
kind: compatibility
governed_by: KDR-0001
statement: >-
  No consumer's domain vocabulary may appear in the engine. Not a type name, not
  an id prefix, not a status value, not a header, not a product name. A consumer
  declares its types in product.config.yaml and adds its rules as a plugin; the
  engine holds only what is true of every graph — loading, schema, ids,
  cross-references, enums, staleness.
rationale: >-
  This is the property the extraction bought. A validator that knows what a
  ledger is has to carry that knowledge for every consumer that does not have
  ledgers, and the next consumer's needs then have to be added to a file the
  first one also ships. Without this constraint the library is a shared script
  with a pip install in front of it, which is the thing it was extracted to stop
  being.
enforced_by: examples/quickstart
---
The test that matters is not in the suite; it is that `examples/quickstart`
models a payments domain with a ledger and a payment term, and nothing about
those words exists in `keelspec/`. The quickstart validates in CI, so the engine
is exercised against a vocabulary it does not contain on every push.

The pressure on this constraint is always the same and always reasonable-sounding:
a rule that two consumers both want, which would be four lines in the engine and
forty in each plugin. The answer is that the engine may gain the *mechanism* both
plugins then use — a way to declare the rule — but not the rule. The test is
whether the addition can be described without naming anything the consumer owns.
If it cannot, it belongs in a plugin.

This constraint is the one a grounding primitive has to satisfy. A checker that
refuses generated text naming things a graph does not contain is squarely the
engine's business; a checker that knows what an `x-fife-` header is, is not. The
caller supplies the surface, the engine supplies the discipline. See FifeRouter's
`grounded-generation`, which is the consumer half of that.
