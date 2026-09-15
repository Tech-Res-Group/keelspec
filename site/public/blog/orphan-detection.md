---
title: Finding the artifacts nobody references — KeelSpec
description: A graph makes absence visible. Orphans are usually either dead weight or a missing link, and both are worth knowing about.
url: https://keelspec.com/blog/orphan-detection.html
---
# Finding the artifacts nobody references

A graph makes absence visible. Orphans are usually either dead weight or a missing link, and both are worth knowing about.

`PAC-020` catches references pointing at nothing. The mirror-image question is just as useful and nobody asks it: which artifacts does *nothing* point at?

## Two kinds of orphan

An orphaned term is either:

**Dead weight.** A concept that mattered once, was superseded, and never removed. It still appears in the glossary, still gets read, and still shapes how newcomers think about the domain -- inaccurately.

**A missing link.** A concept that genuinely matters but that no rule or feature declares a dependency on, which usually means the graph is under-connected rather than the term being useless.

Both are worth surfacing. Neither should fail the build, because a brand-new term is legitimately unreferenced for a while.

## A warning, not an error

This is what warning severity is for:

```
@reg.validator
def orphan_terms(bundle, config, root, report):
    referenced = {
        t for term in bundle["terms"] for t in (term.get("see_also") or [])
    } | {
        t for rule in bundle["rules"] for t in (rule.get("mentions") or [])
    }
    for term in bundle["terms"]:
        if term["id"] not in referenced:
            report.add("PAC-901", "term is referenced by nothing",
                       term["_file"], severity="warning")
```

Warnings print and do not gate. Review them periodically rather than reacting to each one -- an orphan is a question, not a defect.

## The report as a health metric

Track the orphan count over time. A slowly rising number means the model is accumulating vocabulary faster than it is connecting it, which is the leading indicator of a glossary drifting back into being a list of words.

A sudden drop usually means someone deleted rather than retired something. Worth a look.

## Other absence checks worth writing

Once you have the pattern, the family is obvious: rules with no feature implementing them, features implementing no rule, decisions affecting nothing, terms defined but never used in any body text.

Each is a few lines in a validator. Each answers a question that is unanswerable against prose, and each tends to find something the first time you run it.

### Related

- [Extending the validator with plugins](/blog/plugins-deep-dive.html)
- [What a dangling reference actually costs](/blog/dangling-references.html)

## Get the next one by email.

Short notes on product-as-code,
 new diagnostic codes, and what breaks in real repositories. Twice a week, unsubscribe in one click.
