---
id: TERM-plugin
term: Plugin
definition: >-
  A Python module a consumer passes with `-p`, registering that repository's own
  validators, bundle transformers and extra outputs. It is how a consumer adds
  rules the engine has no business knowing.
aka: [product_hooks.py]
see_also: [TERM-diagnostic-code]
---
FifeRouter's plugin holds its definition of done — a shipped feature needs a PR
link, a code link, a resolving test per acceptance criterion, a deployment and a
monitor. None of that is in the engine, because none of it is true of every
graph: a library has no deployment manifest and nothing to probe.

The boundary is [`BR-plugins-extend-never-fork`](../rules/BR-plugins-extend-never-fork.md),
and the reason it exists is [`CON-core-holds-no-consumer-vocabulary`](../constraints/CON-core-holds-no-consumer-vocabulary.md).
