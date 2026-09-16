---
id: BR-the-committed-bundle-is-the-contract
title: The generated bundle is committed, and a stale one fails the build
statement: >-
  The compiled bundle is checked in alongside the artifacts it was generated
  from, and `validate` fails with PAC-060 when the two disagree. A build is
  byte-identical across runs given the same inputs, so the diff is a real signal
  rather than churn.
invariant: >-
  Two builds of the same tree produce the same bytes, and the committed bundle
  either matches the tree or the gate fails.
enforced_by:
  - tests/test_keelspec.py::test_stale_bundle_pac060
  - tests/test_keelspec.py::test_build_is_deterministic
  - tests/test_keelspec.py::test_cli_build_is_deterministic_across_runs
  - tests/test_keelspec.py::test_staleness_reports_which_artifacts_differ
---
Committing a generated file is a thing most projects are right to avoid, so the
reason this one is different is worth stating. The bundle is what the consumer's
app, site or documentation actually renders. If it is generated at deploy time,
a change to intent reaches readers without passing through review, and a broken
cross-reference is discovered by a reader rather than by CI.

Committed, the bundle appears in the diff. A reviewer sees that a rule's wording
changed and that the rendered surface changed with it, in one place. That only
works if the build is deterministic — a bundle that reorders its own keys between
runs produces a diff on every PR, everyone learns to skim it, and the gate is
worth nothing by the second week.

This rule has no governing decision because it predates the extraction; it came
out of the payments platform with the mechanism and has never been argued about.
