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
enforced_by:
  - scripts/check_code_stability.py
  - tests/test_code_stability.py
---
The check installs the newest released keelspec from PyPI and compares its code
table against the working copy's. A code that was released and is now absent
fails the build unless it appears in `RETIRED` in `keelspec/diagnostics.py`, and
a number in `RETIRED` that is registered again fails too. Retiring a code is
allowed; forgetting that you did is not.

What it deliberately does not fail on is a reworded message. Whether new wording
still means the same thing is a judgement, and requiring byte equality would fail
on a typo fix and teach everyone to bypass the gate — which would cost more than
the wording drift it caught. Rewordings and new codes are printed so a reviewer
sees them.

The reason this needs a *different* version of the library rather than a test is
that this repository validates itself. A schema change and the tree that
satisfies it arrive in the same commit, so the local gate always agrees with the
local engine. The only version that can disagree is one already in a consumer's
lockfile.

The gaps this produces in the numbering are information. A missing number says a
rule was retired, which is a thing a reader of an old CI log needs to know.
