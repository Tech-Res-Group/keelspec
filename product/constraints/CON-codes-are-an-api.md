---
id: CON-codes-are-an-api
title: A released diagnostic code keeps its meaning permanently
kind: compatibility
governed_by: KDR-0002
statement: >-
  A diagnostic code that has appeared in a release keeps its meaning for the life
  of the library. A retired rule burns its number: the code is no longer emitted
  and is never reassigned, no neighbouring code is renumbered to close the gap,
  and no existing code changes what it means. PAC-0xx through PAC-06x belong to
  the engine; consumers register their own rules from PAC-9xx.
rationale: >-
  Codes are the part of this library that consumers build on — CI allowlists,
  triage rules, dashboards, plugin ranges. Renumbering one breaks every consumer
  and produces no error anywhere: an allowlist keyed on the old number stops
  matching in silence, and a suppression that was scoped to one rule quietly
  moves to another.
---
Not enforced by a test, and that is worth being explicit about rather than
leaving as an omission. Nothing in the suite compares today's code table against
a released one, so the only thing standing between this constraint and a
well-meant tidy-up is that it is written down.

A test could exist: the released package is on PyPI, so a check could import the
last release's code table and assert that every code present in it still means
what it meant. That would turn this from a convention into a gate. Until it does,
treat a diff that touches an existing key in `keelspec/diagnostics.py` as a
release-blocking change rather than a refactor.

The gaps this produces in the numbering are information. A missing number says a
rule was retired, which is a thing a reader of an old CI log needs to know.
