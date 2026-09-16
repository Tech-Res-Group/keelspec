---
id: BR-plugins-extend-never-fork
title: A consumer's rules are a plugin, never a fork
governed_by: KDR-0001
statement: >-
  Everything specific to how one repository proves intent against delivery lives
  in that repository's plugin — its definition of done, its traceability checks,
  its roadmap model. The engine is installed from PyPI at an exact version and is
  not edited in place by its consumers.
invariant: >-
  A plugin may register validators, transform the bundle and add outputs. It may
  not remove or reinterpret an engine rule, and its diagnostic codes live in the
  consumer range (PAC-9xx).
enforced_by:
  - tests/test_keelspec.py::test_plugin_validator_and_transformer_and_output
  - tests/test_keelspec.py::test_plugin_extra_outputs_are_staleness_gated
  - tests/test_keelspec.py::test_a_plugin_without_register_fails_loudly
---
The pull towards a fork is strongest at exactly the moment a consumer is in a
hurry: the engine is one line away from doing what this repository needs, the
plugin API would take an afternoon, and the repository already has a copy of the
source in its virtualenv.

What makes it a rule rather than advice is that a fork is undetectable from the
consumer side. Everything keeps working, the pin still reads `keelspec==0.7.0`,
and the divergence is only discovered at the next upgrade — which is the point at
which nobody remembers what was changed or why. FifeRouter and KibiPay were both
vendored copies once, and the reconciliation cost is recorded in KDR-0002: it is
the reason the only diagnostic-code renumbering in this library's history
happened.

A plugin that finds it cannot express something is a gap in the plugin API and
should be reported as one.
