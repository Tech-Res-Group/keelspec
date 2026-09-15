---
title: One lifecycle, not two — KeelSpec
description: PDLC and SDLC in one repository, behind one gate, with a reproducible audit trail. Checks on every edge where product intent fans out into code, tests and docs.
url: https://keelspec.com/lifecycle.html
---
# One lifecycle, not two.

Most organisations run a **product development lifecycle (PDLC)**
 and a **software development lifecycle (SDLC)** side by side, connected by
 meetings. The SDLC has been mechanised for thirty years — compilers, type checkers,
 tests, continuous integration (CI). The PDLC has almost none of it. KeelSpec puts both in
 the same repository, behind the same gate, with the same evidence trail.

**What ships today:** `keelspec
 orchestrate` runs ST-01 to ST-06, and `keelspec
 validate` is ST-08. Assembling a pull request (ST-07) and reading production
 back into intent (ST-10) are your pipeline's job — the library has no git,
 no network and no way to merge, by design.

## Your code has a compiler. Your product model has hope.

### Mechanised

A rename breaks every caller, loudly, in seconds. Types are checked, tests run on
 every push, and nothing merges red. Nobody argues about whether this is worth it.

### Unmechanised

A concept changes meaning and every document that assumed the old one stays
 syntactically perfect and semantically wrong. No tool can see the dependency, because
 it was written in English.

### The fix is not discipline

It is the same fix the SDLC already made: declare the structure, check it on every
 change, and fail the build when it stops being true.

## Checks live on the edges.

Intent fans out. A rule becomes a feature, a ticket, an implementation, a
 test, a doc page, a support macro. Every one of those edges is where drift enters, and
 every one of them can carry a check.

### The intent graph

Required fields, id integrity, allowed values, and every reference resolving.
 Shipped in the core, running today.

### Intent to build

The committed bundle still matches the sources that produced it — so what you
 ship and what you wrote cannot silently part company.

### Product to code

The boundary nothing else checks. Does this feature's claimed source path still
 exist? Does every business rule have a test that names its id? Written as plugin
 validators in your own code range.

### The boundary check, in eight lines

```
@reg.validator
def code_paths_exist(bundle, config, root, report):
    for f in bundle["features"]:
        for path in f.get("code") or []:
            if not (root / path).exists():
                report.add("PAC-900",
                           f"missing {path}",
                           f["_file"])
```

A feature that claims code which
 no longer exists is a documented product that is not the shipped product. That is one
 validator, and it is the whole category in miniature.

## Evidence, not screenshots.

The question an auditor actually asks is: how do you
 know your documented rules match your implementation, and can you prove it for any date?
 Most organisations answer with a screenshot of a wiki page.

### The record is the repository

Every artifact is a file, every change is a reviewed commit with an author and a
 timestamp, and every state is recoverable by checking out a SHA. There is no separate
 system of record to reconcile, because the record is the thing itself.

### The control is the gate

`keelspec validate` runs on every pull request (PR) and its exit code decides
 whether the change merges. That is a control with an enforcement mechanism, not a
 policy document asking people to be careful.

### The evidence is reproducible

Bundles are byte-stable: sorted keys, fixed formatting, no timestamps. Check out any
 commit, rebuild, and get identical bytes. An assertion about what the product model
 was on a given date is verifiable rather than asserted.

### The record is exportable

`keelspec evidence -o build/evidence.json` emits what was checked, when,
 on which commit, and with what result — every artifact, the config and the
 bundle carrying a SHA-256. An auditor verifies it by recomputing digests, not by
 trusting the issuer. For a date in the past, check out that commit and run it again.

### The findings are stable

Diagnostics carry codes that are never renumbered, so a control can be described
 once and matched on forever — by CI, by a dashboard, or by whoever is asking.

This is why the engine
 was built inside a payments platform first. In a regulated domain the distance between
 "what we documented" and "what we shipped" is not an inconvenience — it is the finding.

## Put both lifecycles behind one gate.

Start with a glossary and one CI step. Add boundary checks when the graph is
 big enough to need them.
