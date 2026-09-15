"""Write blog posts 11-20 as product-as-code artifacts."""
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "content" / "posts"
OUT.mkdir(parents=True, exist_ok=True)

POSTS = {}

POSTS["POST-adr-and-product-as-code"] = ("""\
title: ADRs, RFCs and where product-as-code fits
slug: adr-and-product-as-code
date: 2026-04-15
summary: Decision records answer why. Product-as-code answers what is true now. Conflating them is why both rot.
author: KeelSpec
category: concept
tags: [decisions, modelling]
related: [POST-business-rules, POST-what-is-product-as-code]
reading_minutes: 4""", """
Architecture decision records are one of the few documentation practices that reliably survives. They work because they are append-only: a decision is made, recorded, and never edited. Superseding one means writing a new record, not rewriting the old.

That immutability is exactly why ADRs cannot carry your current product model.

## Two different questions

An ADR answers **why did we choose this, and what did we know at the time**. Its value is historical. Reading a three-year-old ADR and finding it out of date is not a defect -- the decision really was made under those conditions.

A glossary answers **what does this word mean right now**. A rulebook answers **what invariants hold right now**. These must be current or they are actively harmful. There is no value in a glossary that documents what a term used to mean.

Teams get into trouble by storing the second kind of content in the first kind of document. The ADR says "we will call this a Payment", the name changes two years later, and the ADR is both correct as history and wrong as reference.

## Keep both, wired together

Model decisions as their own collection, with their own lifecycle:

```yaml
- name: decisions
  dir: decisions
  id_prefix: "ADR-"
  required: [id, title, status, date]
  fields: [title, status, date, supersedes, affects]
  enums:
    status: [proposed, accepted, superseded]
  references:
    - field: supersedes
      to: decisions
    - field: affects
      to: rules
```

Now `supersedes` is checked, so an ADR cannot claim to replace one that does not exist. `affects` links the decision to the invariants it changed, which is the query people actually want: *why is this rule the way it is?*

## The division of labour

- **Decisions** are immutable and dated. Never edit them; supersede them.
- **Terms and rules** are current and edited freely. Their history lives in git.

Both are typed artifacts in the same graph, and the references between them are validated. What you get is a current model you can trust, with a traceable path back to the reasoning -- without either document pretending to be the other.
""")

POSTS["POST-migrating-a-wiki"] = ("""\
title: Migrating a wiki to product-as-code
slug: migrating-a-wiki
date: 2026-04-22
summary: How to move years of accumulated pages without a six-month project or a big-bang rewrite.
author: KeelSpec
category: practice
tags: [migration, adoption]
related: [POST-getting-started, POST-plugins-deep-dive]
reading_minutes: 5""", """
The instinct is to model everything first. Resist it. Every large migration that starts with a complete schema stalls, because the schema is wrong in ways you cannot discover without content in it.

Start with one collection and one check.

## Step one: the glossary, nothing else

Pick the glossary. It is the smallest collection, the one with the clearest shape, and the one whose rot causes the most confusion.

```yaml
product_dir: product
output: build/product.generated.json
types:
  - name: terms
    dir: terms
    id_prefix: "TERM-"
    required: [id, term, definition]
    fields: [term, definition, see_also]
    references:
      - field: see_also
        to: terms
```

Move the terms. Do not improve them yet -- copy them across as they are. Improving and migrating at the same time makes it impossible to tell which change broke what, and it triples the review burden.

## Step two: turn on the gate before you feel ready

Add `keelspec validate` to CI while the glossary is still incomplete. The gate does not care that you have twelve terms instead of two hundred. What it does is stop the twelve from rotting while you migrate the rest.

Teams that wait until the migration is complete before enabling the gate spend the whole migration re-fixing things.

## Step three: let the failures design your schema

Now migrate a second collection and let the validator argue with you. You will discover that half your "rules" are decisions, that `status` needs an enum because four spellings of "in progress" exist, and that two terms have the same name in different contexts.

Every one of those is a modelling discovery you could not have made on a whiteboard. This is why the incremental order matters.

## Step four: bespoke checks become plugins

Eventually you will want something the config cannot express -- that a feature's `code` path exists on disk, that no rule is orphaned, that every term appears in at least one feature. Write a plugin, register codes in your own `9xx` range, and the checks join the same report.

This is the step that lets a large legacy project migrate with **no loss of functionality**, because whatever your old homegrown script checked, a plugin can check too.

## What to leave behind

Not everything belongs. Meeting notes, retrospectives, onboarding guides, runbooks -- these are prose with no structural claims, and forcing them into artifacts adds ceremony without adding checks.

Migrate what other things depend on. Leave what only humans read.
""")

POSTS["POST-plugins-deep-dive"] = ("""\
title: Extending the validator with plugins
slug: plugins-deep-dive
date: 2026-04-29
summary: Validators, bundle transformers, extra outputs and custom codes -- the four hooks, and when to reach for each.
author: KeelSpec
category: reference
tags: [plugins, extensibility]
related: [POST-diagnostic-codes-as-api, POST-migrating-a-wiki]
reading_minutes: 5""", """
The config file handles schema, ids, enums and references. Everything beyond that is a plugin -- a single Python file that registers hooks, loaded with `-p`.

```bash
keelspec -p product_hooks.py validate
```

There are four hooks, and choosing the right one matters more than the code you write in it.

## Validators, for checks

A validator receives the loaded bundle and a report, and adds findings. Use it for anything the config cannot express, especially checks that touch the world outside the artifacts.

```python
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

```python
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

```python
reg.extra_output("build/catalogue.json", render_catalogue)
```

The staleness gating is the important half. A generated file that nothing verifies will fall behind.

## Custom codes, for your report

Register your codes so they document themselves and appear in the same report as the core set:

```python
register("PAC-900", "links.code path does not exist on disk")
```

Keep them in a project range like `9xx`. Re-registering a core number overrides its documentation, which is supported deliberately -- a project that wants its own meaning for a number can have it -- but it is rarely what you want.

## When not to write a plugin

If the check is about *taste*, do not. Plugins run in the gate, and the gate blocks merges. A validator that flags short definitions will be wrong constantly and teach people to bypass the gate.

Check facts. Leave judgement to review.
""")

POSTS["POST-llm-context"] = ("""\
title: Feeding an LLM your product truth
slug: llm-context
date: 2026-05-06
summary: A validated bundle is the best context you can give a model, precisely because something guarantees it is current.
author: KeelSpec
category: practice
tags: [llm, context]
related: [POST-docs-from-bundles, POST-what-is-product-as-code]
reading_minutes: 4""", """
Retrieval over a wiki has a failure mode nobody likes to name: the model faithfully retrieves a document that is two years out of date and answers with total confidence.

The retrieval worked. The index worked. The embedding worked. The content was wrong, and no part of the pipeline was responsible for noticing.

## Currency is a property of the source

You cannot fix stale context downstream. Reranking does not know what is true. A larger context window just includes more stale documents. Prompting the model to "only use current information" asks it to determine something it cannot possibly determine.

The only place currency can be established is at the source, before retrieval exists.

This is what a validated bundle gives you. Not that it is *correct* -- no tool can promise that -- but that it is *internally consistent and not stale relative to its sources*. Every reference resolves. Every enum is in range. The compiled artifact matches the markdown that produced it, because CI refuses to merge otherwise.

## The bundle is already the right shape

`product.generated.json` is structured, typed, and complete. That makes it far better raw material than scraped HTML:

- **Slice by type.** Answering a terminology question? Send the terms collection. You do not need a vector search to know that.
- **Traverse instead of guessing.** The graph is explicit, so pulling a rule and the features it applies to is a lookup, not a similarity gamble.
- **Cite precisely.** Every record has an id and a `_file`. Answers can point at `BR-idempotent` in a specific file, which a reader can verify.
- **Cache it.** The bundle changes on merges, not continuously. It is an ideal stable prefix for prompt caching.

## Small enough to skip retrieval

Most product models are smaller than people assume. A few hundred artifacts is a few hundred kilobytes -- comfortably inside a modern context window.

If the whole model fits, retrieval is a step you can delete. No index to rebuild, no staleness between the index and the source, no chunking artefacts. Send the collection, ask the question.

Retrieval is a compression strategy for context that does not fit. Check whether yours does not fit before building the machinery.

## The honest limitation

None of this makes a model correct. It removes one specific failure -- answering from a document that stopped being true -- and leaves every other failure exactly where it was.

That is still worth having, because it is the failure users find hardest to detect.
""")

POSTS["POST-review-culture"] = ("""\
title: Reviewing product changes in pull requests
slug: review-culture
date: 2026-05-13
summary: When intent lives in the repository, product decisions get the same review rigour as code. That changes the conversation more than the tooling does.
author: KeelSpec
category: practice
tags: [workflow, culture]
related: [POST-ci-gate-anatomy, POST-committing-generated-bundles]
reading_minutes: 4""", """
The mechanical benefits of product-as-code are easy to describe. The cultural one is larger and harder to sell in advance: product decisions become reviewable.

## What changes

A definition change is now a diff. Someone proposes that "settlement" means something slightly different, and instead of editing a wiki page silently at 4pm, they open a pull request. The people who care get notified. The change is discussed in the open, against a specific proposed wording, and the discussion is attached to the change forever.

Compare that to the wiki, where the same edit is invisible unless you happen to watch the page, and the reasoning exists only in whatever meeting produced it.

## The gate carries the boring half

The reason this is bearable is that the machine handles everything mechanical. Reviewers never check whether ids are unique, references resolve, or the bundle was rebuilt. Those are `PAC-01x`, `PAC-020` and `PAC-060`, and they are settled before a human looks.

What remains for the reviewer is the only thing a human is better at: **is this true, and is it the right call?**

That is a good use of attention. Most review processes fail because they spend it on things a script could have done.

## Blast radius is visible

Because the bundle is committed, the diff shows the consequence. Adding one `see_also` changes one line. Restructuring a type changes four hundred. A reviewer sees the size of the change before merging, which is exactly the signal that free-form documents never provided.

## Who should review what

Terms and rules need domain review, not engineering review. The people who should approve a change to `TERM-settlement` are the ones who will be wrong if it is wrong -- which usually means finance, or support, or whoever answers customer questions about it.

`CODEOWNERS` handles this. Point `product/terms/` at the domain group. Now the right people are pulled in automatically, and the ones who do not care are not.

## The failure mode to watch

Review can become a bottleneck if every trivial wording fix needs three approvals. Keep the required-reviewer set small and let the gate do the enforcing. The goal is that changes are *visible*, not that they are *slow*.

Visibility is the product. Ceremony is a cost you should keep paying down.
""")

POSTS["POST-enums-and-lifecycles"] = ("""\
title: Modelling lifecycles with enums
slug: enums-and-lifecycles
date: 2026-05-20
summary: Four spellings of in-progress is not a naming problem. It is a missing constraint, and PAC-030 is the fix.
author: KeelSpec
category: practice
tags: [modelling, schema]
related: [POST-business-rules, POST-typed-artifacts]
reading_minutes: 3""", """
Every artifact collection acquires a status field. Every uncontrolled status field acquires variants: `in progress`, `in-progress`, `In Progress`, `wip`, `started`, and eventually `in-progres`.

Then someone writes a dashboard, filters on one spelling, and reports numbers that are quietly wrong.

## Declare the set

```yaml
- name: features
  dir: features
  enums:
    status: [proposed, in-progress, shipped, retired]
```

Anything outside the set is `PAC-030`, with the offending value and the allowed list in the message:

```
PAC-030  status 'in-progres' not in ['in-progress', 'proposed', 'retired', 'shipped']
```

The typo is caught the moment it is written, by the person who wrote it. Nobody audits anything.

## Design the states, not the vocabulary

The valuable part is not spelling enforcement -- it is being forced to decide what the states *are*. Teams usually discover during this exercise that they have been using one field for two concepts: where something is in the build process, and whether it is available to customers. Those are different lifecycles and want different fields.

Keep the set small. Four or five states is usually right. A twelve-state lifecycle means the field is doing several jobs, and every consumer will have to know which states group together.

## Retired, not deleted

Include a terminal state and prefer it to deletion. Deleting a retired feature breaks every rule and decision that referenced it -- correctly, since `PAC-020` will say so -- and destroys the record of why it existed.

Marking it `retired` keeps the graph intact, keeps the history readable, and lets consumers filter it out. Deletion is for things created in error.

## Changing the set later

Adding a state is safe. Removing or renaming one is a graph-wide change: tighten the enum, run `validate`, and get the list of every artifact using the old value. Fix them in the same pull request.

That is a five-minute job with a validator and a genuinely unbounded one without. It is the same story as renaming an id -- mechanical and complete, rather than manual and hopeful.
""")

POSTS["POST-payments-case-study"] = ("""\
title: What we learned running this in payments
slug: payments-case-study
date: 2026-05-27
summary: KeelSpec was extracted from a payments platform running 39 features and a 283 KB bundle. Here is what survived contact with production.
author: KeelSpec
category: case-study
tags: [case-study, production]
related: [POST-plugins-deep-dive, POST-the-staleness-gate]
reading_minutes: 5""", """
KeelSpec did not begin as a tool. It began as the product-as-code engine inside the pharthing / KibiPay payments platform, and it was extracted so other teams could use it. That order matters: every feature exists because something went wrong without it.

## The numbers

39 features under the gate, a concept catalogue, a rulebook, and a compiled render bundle of about 283 KB. `keelspec validate` is the sole product gate in CI, running through a plugin that adds domain-specific checks.

The extraction was verified by a **byte-identical parity test**: the extracted engine produces exactly the bundle the in-house one did. Not equivalent -- identical. That test is the reason the extraction could be trusted, and it is only possible because the build is deterministic.

## What earned its place

**The staleness gate.** In a domain where a business rule is the difference between a correct ledger and an incident, a spec that has silently diverged from the build is a real risk. `PAC-060` fires more often than any other code during normal work, almost always because someone edited an artifact and forgot to rebuild. Fourteen seconds of CI, every time.

**Typed references.** The concept graph in payments is dense -- settlement references clearing references reconciliation. Renames happen, because the domain vocabulary genuinely improves as the team learns it. Every rename is mechanical because `PAC-020` produces the exact list of what to update.

**Plugins.** The platform's own checks -- that a feature's claimed code paths exist, that reverse edges are computed for the renderer, that a runtime catalogue is emitted -- are all plugin hooks. None of them are in the core tool, and none of them required forking it. This is the mechanism that let a large existing project adopt the extracted engine without losing anything.

## What we got wrong first

**Too much schema, too early.** The first version had required fields nobody could reliably supply, so artifacts accumulated placeholder values. Placeholder values are worse than missing ones: they look like data. The fix was to require less and add constraints only once the content proved they held.

**Checks that needed judgement.** An early validator flagged definitions under a certain length. It was wrong often enough that people started reaching for the bypass, which briefly put the whole gate at risk. It was deleted. Gates check facts.

**Ids encoding structure.** Early ids embedded team and grouping. Both changed within a year. Now ids are flat and semantic, and the changeable parts are fields.

## The honest summary

The tool is small because the useful part is small. Most of the value is in two checks -- do references resolve, and does the build match its sources -- run automatically on every change. Everything else is ergonomics around those two questions.
""")

POSTS["POST-docs-from-bundles"] = ("""\
title: Rendering docs sites from one bundle
slug: docs-from-bundles
date: 2026-06-03
summary: One compiled artifact, many surfaces. The point is not convenience -- it is that the surfaces cannot disagree.
author: KeelSpec
category: practice
tags: [docs, rendering]
related: [POST-llm-context, POST-committing-generated-bundles]
reading_minutes: 4""", """
Most organisations have the same concept explained in four places: the public docs, the in-app help, an internal wiki, and a slide deck. All four were correct when written. At least two are wrong now.

The problem is not that there are four surfaces. Users legitimately need different depth in different contexts. The problem is four independent *sources*.

## One source, many renderers

Compile once, render many times. `product.generated.json` is the source; each surface is a rendering of it.

- The public docs site renders terms and features as pages
- The app renders definitions as tooltips from the same terms
- An internal catalogue renders the full graph with cross-links
- The LLM context is a slice of the same JSON

None of these hold their own copy. Change a definition, rebuild, and every surface updates on the next deploy.

## The blog you are reading

This site does it too. The posts are typed artifacts under `content/posts/`, with a `product.config.yaml` declaring their shape: ids must match filenames, `category` must be in the allowed set, and every `related` link must resolve to a real post.

`keelspec build` compiles them to `blog.generated.json`. A short renderer turns that into static HTML. If a post referenced a slug that did not exist, `PAC-020` would fail the build rather than shipping a dead link.

The blog is a demo of the product it describes, which is the only honest way to sell a tool like this.

## Rendering is boring on purpose

The renderer should be a template loop over a JSON file. If it is doing anything clever -- inferring structure, parsing prose, guessing relationships -- that logic belongs in a bundle transformer, computed once at build time and committed.

Consumers should not contain knowledge about the model. That is how the four-sources problem comes back in a new costume.

## What stays separate

Not everything should render from the bundle. Tutorials, narrative guides and onboarding material are prose whose value is the sequencing. Trying to generate them from artifacts produces something technically accurate and unreadable.

Generate the reference material. Write the guides. Link the guides to artifact ids so a validator can tell you when a guide references something that no longer exists.
""")

POSTS["POST-orphan-detection"] = ("""\
title: Finding the artifacts nobody references
slug: orphan-detection
date: 2026-06-10
summary: A graph makes absence visible. Orphans are usually either dead weight or a missing link, and both are worth knowing about.
author: KeelSpec
category: practice
tags: [graph, plugins]
related: [POST-plugins-deep-dive, POST-dangling-references]
reading_minutes: 3""", """
`PAC-020` catches references pointing at nothing. The mirror-image question is just as useful and nobody asks it: which artifacts does *nothing* point at?

## Two kinds of orphan

An orphaned term is either:

**Dead weight.** A concept that mattered once, was superseded, and never removed. It still appears in the glossary, still gets read, and still shapes how newcomers think about the domain -- inaccurately.

**A missing link.** A concept that genuinely matters but that no rule or feature declares a dependency on, which usually means the graph is under-connected rather than the term being useless.

Both are worth surfacing. Neither should fail the build, because a brand-new term is legitimately unreferenced for a while.

## A warning, not an error

This is what warning severity is for:

```python
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
""")

POSTS["POST-getting-started"] = ("""\
title: Product-as-code in thirty minutes
slug: getting-started
date: 2026-06-17
summary: A working glossary, a rulebook, and a CI gate, starting from an empty directory.
author: KeelSpec
category: practice
tags: [tutorial, adoption]
related: [POST-migrating-a-wiki, POST-what-is-product-as-code]
reading_minutes: 5""", """
The fastest way to understand this is to run it. Thirty minutes, start to finish.

## Install

```bash
pip install keelspec
```

Or scaffold a complete repository -- config, example artifacts and the CI gate -- in one command:

```bash
pipx run copier copy --trust gh:Tech-Res-Group/keelspec my-product-repo
```

`--trust` lets the template run `keelspec build` once so the new repository is valid on its first commit.

## Declare two types

`product.config.yaml`:

```yaml
product_dir: product
output: build/product.generated.json
types:
  - name: terms
    dir: terms
    id_prefix: "TERM-"
    required: [id, term, definition]
    fields: [term, definition, see_also]
    references:
      - field: see_also
        to: terms
  - name: rules
    dir: rules
    id_prefix: "BR-"
    required: [id, title, statement]
    fields: [title, statement]
```

## Write an artifact

`product/terms/TERM-payment.md`:

```markdown
---
id: TERM-payment
term: Payment
definition: An instruction to move money between two parties.
see_also: [TERM-ledger]
---
The canonical unit of work in the system.
```

Note `see_also` points at `TERM-ledger`. Build now and it fails, because that term does not exist yet -- which is the tool working correctly. Write it, or drop the reference.

## Build and validate

```bash
keelspec build       # -> build/product.generated.json  (commit it)
keelspec validate    # schema + graph + staleness
```

`validate` exits non-zero when it finds errors. That exit code is the entire contract.

## Gate it

```yaml
name: product-as-code
on: [pull_request, push]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Tech-Res-Group/keelspec@v0.1.0
```

Commit the bundle alongside the artifacts. That is what makes staleness detectable.

## Now break it on purpose

Worth five minutes: rename `TERM-ledger` and push. Watch `PAC-020` name the file that still references the old id. Delete a required field and watch `PAC-001`. Edit the committed bundle by hand and watch `PAC-060`.

Seeing the failures is what makes the value concrete. Everything after this is adding collections and, eventually, a plugin.
""")

for pid, (front, body) in POSTS.items():
    (OUT / f"{pid}.md").write_text(f"---\nid: {pid}\n{front}\n---\n{body}", encoding="utf-8", newline="\n")

print(f"wrote {len(POSTS)} posts")
