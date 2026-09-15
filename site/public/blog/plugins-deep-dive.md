---
title: Extending the validator with plugins — KeelSpec
description: Validators, bundle transformers, extra outputs and custom codes -- the four hooks, and when to reach for each.
url: https://keelspec.com/blog/plugins-deep-dive.html
---
# Extending the validator with plugins

Validators, bundle transformers, extra outputs and custom codes -- the four hooks, and when to reach for each.

The config file handles schema, ids, enums and references. Everything beyond that is a plugin -- a single Python file that registers hooks, loaded with `-p`.

```
keelspec -p product_hooks.py validate
```

There are four hooks, and choosing the right one matters more than the code you write in it.

## Validators, for checks

A validator receives the loaded bundle and a report, and adds findings. Use it for anything the config cannot express, especially checks that touch the world outside the artifacts.

```
@reg.validator
def code_paths_exist(bundle, config, root, report):
    for f in bundle["features"]:
        for path in f.get("code") or []:
            if not (root / path).exists():
                report.add("PAC-900", f"missing {path}", f["_file"])
```

That one check -- does the source path this feature claims actually exist -- catches a surprising amount of drift, because features get deleted and their documentation does not.

## Bundle transformers, for derived data

A transformer enriches the bundle in place before it is written. Reverse edges are the canonical case: artifacts declare `applies_to` in one direction, and consumers want the other.

```
@reg.bundle_transformer
def reverse_edges(bundle, config, root):
    for rule in bundle["rules"]:
        for fid in rule.get("applies_to") or []:
            feature = find(bundle["features"], fid)
            feature.setdefault("_rules", []).append(rule["id"])
```

Compute it once at build time rather than in every consumer. The derived field is part of the committed bundle, so it is staleness-gated like everything else.

## Extra outputs, for other shapes

Some consumers want a different file entirely -- a search index, a runtime catalogue, a flat CSV for a spreadsheet. Register it and it is generated on `build` and staleness-checked on `validate`:

```
reg.extra_output("build/catalogue.json", render_catalogue)
```

The staleness gating is the important half. A generated file that nothing verifies will fall behind.

## Custom codes, for your report

Register your codes so they document themselves and appear in the same report as the core set:

```
register("PAC-900", "links.code path does not exist on disk")
```

Keep them in a project range like `9xx`. Re-registering a core number overrides its documentation, which is supported deliberately -- a project that wants its own meaning for a number can have it -- but it is rarely what you want.

## When not to write a plugin

If the check is about *taste*, do not. Plugins run in the gate, and the gate blocks merges. A validator that flags short definitions will be wrong constantly and teach people to bypass the gate.

Check facts. Leave judgement to review.

### Related

- [Diagnostic codes are an API](/blog/diagnostic-codes-as-api.html)
- [Migrating a wiki to product-as-code](/blog/migrating-a-wiki.html)

## Get the next one by email.

Short notes on product-as-code,
 new diagnostic codes, and what breaks in real repositories. Twice a week, unsubscribe in one click.
