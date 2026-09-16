---
id: TERM-bundle
term: Bundle
definition: >-
  The compiled JSON output of a tree: every artifact, its fields, its body and
  its resolved edges, written to the path named by `output` and committed
  alongside the artifacts it came from.
aka: [generated bundle, product.generated.json]
see_also: [TERM-artifact]
---
The bundle is what applications read. A consumer's site, docs page or console
renders the bundle rather than parsing markdown, which is what makes product
intent something a product can display without knowing how it is stored.

It is committed on purpose and gated on staleness — see
[`BR-the-committed-bundle-is-the-contract`](../rules/BR-the-committed-bundle-is-the-contract.md).
