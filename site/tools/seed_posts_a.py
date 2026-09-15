"""Write blog posts 1-10 as product-as-code artifacts."""
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "content" / "posts"
OUT.mkdir(parents=True, exist_ok=True)

POSTS = {}

POSTS["POST-what-is-product-as-code"] = ("""\
title: What product-as-code actually means
slug: what-is-product-as-code
date: 2026-02-04
summary: Not docs in a repo. Typed artifacts with a schema, a reference graph, and a build that fails when they stop being true.
author: KeelSpec
category: concept
tags: [product-as-code, fundamentals]
related: [POST-why-specs-rot, POST-typed-artifacts]
reading_minutes: 5""", """
Most teams that say they do "docs as code" mean they moved their markdown into git. That is a storage decision, and storage was never the problem. The problem is that nothing checks the documents against reality, so they drift, and drift is invisible until someone acts on a stale sentence.

Product-as-code is a stronger claim: your product intent is a **typed, validated graph** that participates in your build.

Three properties make it real.

## It is typed

A glossary term is not a paragraph. It is a record with an id, a term, a definition, and optionally a list of related terms. Declaring that shape means a term missing its definition is a build error, not something a reader discovers eighteen months later.

You declare your own types. There is no universal schema for product intent, and any tool that ships one is wrong about your domain. Terms, business rules, features, decisions, personas, risks, invariants -- you name the collections and the fields.

## It is a graph

Artifacts reference each other. A feature implements a rule. A term relates to another term. A decision supersedes an earlier decision.

Once those references are declared rather than written as prose, they can be *checked*. Rename a term and every artifact pointing at the old id becomes a build failure with a filename attached. This is the single highest-value property of the whole approach, and it is impossible with free-form documents, because prose links are invisible to machines.

## It compiles, and the compilation is gated

The artifacts compile to one JSON bundle. Your docs site renders from it. Your app's in-product glossary renders from it. The context you hand an LLM comes from it. Because there is exactly one compiled artifact, those surfaces cannot disagree.

And the bundle is committed, which is the part people find odd until they see why: if the bundle only exists inside CI, nothing can prove that what you ship matches what you wrote. Committing it turns invisible drift into a visible diff on a pull request.

## What this is not

It is not a replacement for your wiki, your PRD template, or your product manager. Prose still matters -- every artifact has a body, and that body is where the thinking lives. What changes is that the *structural* claims get enforced while the prose stays free.

It is also not a process. Nobody has to adopt a methodology. You add a config file, write some markdown with frontmatter, and put one command in CI. If it fails, something is genuinely inconsistent.

That is the whole idea. The rest is detail.
""")

POSTS["POST-why-specs-rot"] = ("""\
title: Why specs rot, and why discipline will not fix it
slug: why-specs-rot
date: 2026-02-11
summary: Documentation decay is a structural problem, not a motivational one. Teams that resolve to try harder produce the same rot, slightly later.
author: KeelSpec
category: concept
tags: [drift, culture]
related: [POST-what-is-product-as-code, POST-the-staleness-gate]
reading_minutes: 4""", """
Every team has had the meeting. The docs are out of date, everyone agrees it is bad, and the remedy proposed is that people should update them. Six months later the docs are out of date and the meeting happens again.

The remedy fails because it misdiagnoses the problem.

## Rot is asymmetric

Writing a document is a discrete act with a deadline attached. Keeping it true is a continuous obligation with no deadline at all. Those are not the same kind of work, and only one of them shows up in a sprint.

Worse, the cost of *not* updating is deferred and diffuse. The person who renames a concept in code pays nothing. The cost lands months later on someone else, usually someone new, who reads a confident sentence and believes it.

Any system where the cost of a mistake lands on a different person than the one making it will accumulate that mistake indefinitely. This is not a character flaw. It is an incentive structure.

## Prose hides its own dependencies

If a function changes signature, every caller breaks loudly. If a concept changes meaning, every document that assumed the old meaning stays syntactically perfect and semantically wrong.

Documents have dependencies -- on terms, on rules, on other documents -- but those dependencies are written in English, so no tool can see them. You cannot get a "who references this" list for a paragraph.

This is why the same team that maintains a rigorous type system tolerates a rotting glossary. They are not being inconsistent. Their tools simply cannot see one of the two.

## Review does not catch it

The reviewer of a pull request sees the diff. A stale document is not in the diff -- that is precisely what makes it stale. Asking reviewers to notice the absence of a change is asking them to hold the entire product model in their head on every review.

## What actually works

Move the structural claims out of prose and into something checkable, then check it on every change. Not because engineers need policing, but because the loop needs closing: the person making the change should find out immediately, while the context is still in their head.

That is the entire mechanism. A rename that breaks three references should fail the build in fourteen seconds, not surface in a support ticket next March.

Discipline is not the input. It is what you get to stop spending.
""")

POSTS["POST-the-staleness-gate"] = ("""\
title: PAC-060, the check nobody else has
slug: the-staleness-gate
date: 2026-02-18
summary: Schema validation is common. Reference checking is rare. Proving the committed build still matches its sources is the one that catches real drift.
author: KeelSpec
category: reference
tags: [diagnostics, ci]
related: [POST-committing-generated-bundles, POST-ci-gate-anatomy]
reading_minutes: 4""", """
KeelSpec emits seven core diagnostic codes. Six of them do what you would expect: required fields, id prefixes, filename agreement, duplicates, enum membership, reference resolution. Useful, unremarkable.

`PAC-060` is the one that earns its place.

## What it checks

The artifacts compile to a JSON bundle, and that bundle is committed to the repository. `PAC-060` recomputes the bundle from the current sources and compares it to the committed one. If they differ, the build fails:

```
PAC-060  build/product.generated.json is stale - run: keelspec build (and commit it)
```

That is it. It is almost embarrassingly simple, and it catches a class of failure that nothing else does.

## Why it matters

Consider what "stale" actually means here. Either:

- somebody edited an artifact and did not rebuild, so what you *ship* is older than what you *wrote*; or
- somebody edited the generated bundle directly, so what you wrote no longer explains what you ship.

Both are drift. Both are silent. Neither is visible in a normal code review, because in the first case the bundle is simply absent from the diff and in the second the source is.

`PAC-060` makes both impossible to merge.

## Determinism is the prerequisite

A staleness check is only usable if the build is byte-stable. If the compiler emits keys in hash order, or embeds a timestamp, the check fires constantly and the team learns to ignore it -- which is worse than not having it.

So the bundle is emitted with sorted keys, a fixed indent, and no timestamps. The same sources always produce the same bytes. That makes a diff on the bundle meaningful: every changed line corresponds to a real change in intent.

This is also why the parity test in the original payments extraction could be byte-identical. Determinism is not a nicety; it is what makes the whole gate trustworthy.

## Plugin outputs too

If a plugin emits extra outputs -- a runtime catalogue, a search index -- those are staleness-gated on exactly the same terms. A generated artifact that can silently fall behind is a generated artifact that will.

## The general principle

Most validation asks "is this document well-formed?" That is the easy question, and it is not where drift lives.

`PAC-060` asks a harder one: does the thing you are shipping still correspond to the thing you wrote? You can only ask that if both are in the repository and the compilation between them is reproducible.

Which is the argument for committing your build output, and the subject of another post.
""")

POSTS["POST-typed-artifacts"] = ("""\
title: Why typed artifacts beat free-form documents
slug: typed-artifacts
date: 2026-02-25
summary: The moment a document has a declared shape, a whole class of question becomes machine-answerable.
author: KeelSpec
category: concept
tags: [schema, modelling]
related: [POST-what-is-product-as-code, POST-naming-ids]
reading_minutes: 4""", """
A free-form document can say anything, which sounds like freedom and behaves like debt.

Give the same content a declared shape -- an id, a set of required fields, an allowed set of values, some typed references -- and questions that were previously research tasks become one-line queries.

## Questions you can suddenly answer

- Which business rules have no feature implementing them?
- Which terms are defined but referenced nowhere?
- Which features claim a status that is not in our lifecycle?
- What breaks if we rename this concept?
- How many artifacts changed in this release, and which?

None of these are exotic. Every one is unanswerable against a folder of prose, and trivial against a typed graph. Not because the prose lacks the information, but because extracting it requires a human to read everything.

## The shape is yours

The important design decision in KeelSpec is that it ships no schema. You declare your collections in `product.config.yaml`:

```yaml
types:
  - name: rules
    dir: rules
    id_prefix: "BR-"
    required: [id, title, statement]
    fields: [title, statement, applies_to]
    references:
      - field: applies_to
        to: features
```

A generic schema would be wrong for everyone. Your domain has concepts that no tool vendor has heard of, and the ones it does ship -- "epic", "story" -- usually encode a methodology you did not choose.

## Types are a conversation, not a cage

In practice the schema evolves, and that is healthy. You start with terms and rules. Someone adds features and wants them to reference rules. Later a lifecycle appears and `status` gets an enum. Each tightening is a small pull request, and the validator immediately tells you which existing artifacts violate the new constraint.

That last part is the quiet benefit. Tightening a schema on a folder of prose is a manual audit. Tightening it on typed artifacts is a build failure with a file list.

## Keep the prose

None of this removes writing. Every artifact has a body below the frontmatter, and the body is where reasoning, nuance, examples and caveats live. Structure the claims that machines can check; leave the thinking in English.

The split is the point: the frontmatter is a contract, the body is a conversation. Enforce the contract, and the conversation gets better because nobody is using it to store facts that should have been fields.
""")

POSTS["POST-dangling-references"] = ("""\
title: What a dangling reference actually costs
slug: dangling-references
date: 2026-03-04
summary: PAC-020 looks like a link checker. It is really a rename detector, and renames are where product knowledge goes to die.
author: KeelSpec
category: reference
tags: [diagnostics, graph]
related: [POST-the-staleness-gate, POST-naming-ids]
reading_minutes: 4""", """
Somebody decides `TERM-payment` was always the wrong word and renames it to `TERM-charge`. One file changed. The pull request looks harmless.

Three other artifacts referenced the old id. Without a check, all three merge pointing at something that no longer exists.

## The failure is silent and slow

Nothing crashes. No test goes red. The rendered glossary shows a link that goes nowhere, or worse, silently omits it. A business rule now cites a concept that cannot be looked up.

Six months later someone reads that rule, cannot find the concept, and reconstructs what they think it meant. Now there are two meanings in circulation, and the team has a subtle and expensive disagreement that nobody can trace to its origin.

That is what a dangling reference costs. Not a broken link -- a fork in the shared model.

## PAC-020

```
PAC-020  product/rules/BR-idempotent.md: applies_to 'TERM-payment'
         does not resolve to a terms id
```

The check runs on every push. The rename above fails in seconds, with the three offending files named, before a reviewer has opened the PR. The author fixes them while the change is still in their head -- which is the only moment when fixing it is cheap.

## Why prose links cannot do this

You could write a markdown link and run a link checker. That catches a missing *file*. It does not catch:

- a file that exists but whose id changed
- a reference to a concept that was merged into another
- a reference that is structurally fine but points at the wrong collection
- a field that should reference a rule but points at a feature

Declared references carry the target *type*. `applies_to` must resolve to a `features` id, and pointing it at a term is an error even though a file exists. A link checker cannot express that, because prose links have no type.

## The compounding effect

The value grows superlinearly with the size of the graph. With twenty artifacts you could audit by hand. With three hundred, spread across a glossary, a rulebook, a feature catalogue and a decision log, nobody has the whole thing in their head -- and that is exactly when confident renames start doing damage.

A reference check turns the graph's size from a liability into an asset. The bigger it gets, the more the machine is doing for you.
""")

POSTS["POST-ci-gate-anatomy"] = ("""\
title: Anatomy of a product CI gate
slug: ci-gate-anatomy
date: 2026-03-11
summary: What a good product gate checks, what it must never do, and why its exit code is the entire contract.
author: KeelSpec
category: practice
tags: [ci, workflow]
related: [POST-the-staleness-gate, POST-review-culture]
reading_minutes: 4""", """
A gate is a program whose exit code decides whether a pull request can merge. That is the whole interface. Everything else -- the output format, the codes, the pretty printing -- is ergonomics layered on top of one bit.

Getting that bit right is mostly about restraint.

## What it should check

**Structural claims only.** Required fields present. Ids well-formed and unique. Enum values in range. References resolving. The committed build matching its sources.

Every one of those is objectively true or false. A machine can decide it without judgement, and a human reading the failure will agree immediately.

## What it must never check

**Anything requiring taste.** Whether a definition is *good*, whether a rule is *wise*, whether a feature *should* exist. Those are review conversations, and a gate that tries to have them will be wrong often enough that people start looking for the bypass flag.

The moment a team routinely skips your gate, you have less than nothing: you have a false sense of coverage.

## Fast, or it will be worked around

A product gate should finish in seconds. It reads some markdown, builds a dict, and compares strings. There is no excuse for it to take a minute. If it is slow, people push and context-switch, and the feedback arrives after they have moved on -- which destroys most of the value.

## Stable codes, not stable prose

Findings carry codes like `PAC-020`. The code is the API; the message is for humans and may be reworded any time. This matters because CI configuration, dashboards and team conventions all end up matching on *something*, and if the only stable thing is prose, every wording improvement breaks somebody's grep.

Never renumber a code. Retire it and add a new one.

## One command

```yaml
- uses: actions/checkout@v4
- uses: Tech-Res-Group/keelspec@v0.1.0
```

The gate should be a single step with no bespoke scripting around it. Every line of glue in a workflow file is a line that rots, and a gate that requires maintenance is a gate that gets deleted during the next CI cleanup.

## Failing well

A good failure names the code, the file, and the specific value that is wrong. A reader should be able to fix it without opening the tool's documentation:

```
ERROR PAC-030 product/features/FEAT-refunds.md: status 'in-progres'
      not in ['done', 'in-progress']
```

That message contains the typo, the file, and the allowed set. Nobody needs to look anything up. That is the standard.
""")

POSTS["POST-diagnostic-codes-as-api"] = ("""\
title: Diagnostic codes are an API
slug: diagnostic-codes-as-api
date: 2026-03-18
summary: Treat your error codes with the same seriousness as your function signatures, because downstream systems depend on both.
author: KeelSpec
category: reference
tags: [diagnostics, design]
related: [POST-ci-gate-anatomy, POST-plugins-deep-dive]
reading_minutes: 3""", """
Compilers learned this decades ago. `error: C2065` means something specific, forever, and an entire ecosystem of tooling depends on it.

Validation tools usually do not learn it, and then wonder why nobody automates around them.

## The contract

KeelSpec's core codes occupy documented ranges:

- `00x` required-field and schema
- `01x` id and graph integrity
- `02x` cross-reference resolution
- `03x` enum and allowed values
- `06x` generated-bundle staleness

The rule is short: **never renumber an existing code.** If a check changes meaning, retire the old number and add a new one. Renumbering silently breaks everything downstream, and it breaks it quietly, which is the worst way.

## What depends on codes

Once codes are stable, useful things become possible:

- CI suppresses a specific class of finding during a migration, without disabling the gate wholesale
- A dashboard tracks `PAC-020` count over time as a health metric
- A pre-commit hook fails on `PAC-06x` only, because staleness is the cheap local check
- A team convention says "`PAC-030` findings block release; warnings do not"

Every one of those is grep on a stable token. None of them survive prose changes.

## Your own range

Projects register their own codes through the plugin system, conventionally in a `9xx` range so they never collide with the core set:

```python
register("PAC-900", "links.code path does not exist on disk")
```

Now your bespoke check is a first-class citizen. It appears in the same report, matches the same patterns, and your dashboard does not care that it came from a plugin.

## Severity is part of the contract too

A finding is an error or a warning, and that classification is as much a promise as the number. Quietly promoting a warning to an error will break someone's build on a Tuesday morning for reasons they cannot see in their own diff. If a check needs to get stricter, that is a new code, or a major version, or an announcement -- ideally all three.

Stability is unglamorous. It is also the entire reason anyone will build on top of your tool.
""")

POSTS["POST-committing-generated-bundles"] = ("""\
title: Commit the generated bundle
slug: committing-generated-bundles
date: 2026-03-25
summary: Build artifacts usually do not belong in git. This one does, and the reason is that it turns invisible drift into a reviewable diff.
author: KeelSpec
category: practice
tags: [ci, workflow]
related: [POST-the-staleness-gate, POST-review-culture]
reading_minutes: 4""", """
"Never commit build output" is good advice that people apply too broadly. It exists because generated files create merge conflicts, bloat history, and go stale. All true, and all worth paying here.

## The argument for

**It makes staleness checkable.** If the bundle only ever exists inside CI, no check can compare what you ship against what you wrote, because only one of them is in the repository. Committing it is what makes `PAC-060` possible at all.

**It makes changes reviewable.** A reviewer sees not just the edited markdown but the compiled consequence. Adding one reference changes one line in the bundle. Restructuring a type changes hundreds. That signal is visible before merge, which is the only time it is cheap.

**It makes consumers simple.** A docs site, an app, or a script can read one JSON file from the repository at a known path, with no build step and no artifact store. That is a real reduction in moving parts.

**It makes history queryable.** `git log` on the bundle is a changelog of your product model. When did this rule appear? Which release added these terms? Ordinary git commands answer it.

## Paying the costs

*Merge conflicts.* Real, and mitigated by determinism. Sorted keys and stable formatting mean two people editing different artifacts touch different regions. When a conflict does happen, the resolution is to rebuild, not to hand-merge -- and `PAC-060` verifies you did.

*History bloat.* JSON compresses well and the file is small. The payments platform this was extracted from runs a 283 KB bundle; the repository does not notice.

*Going stale.* This is the objection the gate exists to answer. A committed artifact that nothing checks does rot. A committed artifact that fails the build when it drifts cannot.

## The rule of thumb

Commit a build artifact when a check depends on comparing it to its sources. Otherwise do not.

That is a narrow rule. It happens to be exactly the situation product-as-code is in, and it is why the advice looks like an exception rather than a contradiction.
""")

POSTS["POST-business-rules"] = ("""\
title: Writing business rules that survive contact with code
slug: business-rules
date: 2026-04-01
summary: A rule that cannot be violated by a specific line of code is not a rule. It is a sentiment.
author: KeelSpec
category: practice
tags: [modelling, rules]
related: [POST-typed-artifacts, POST-enums-and-lifecycles]
reading_minutes: 4""", """
Most documents labelled "business rules" contain a mixture of three things: actual invariants, product decisions, and encouragement. Only the first kind is worth the ceremony of an id.

## The test

A business rule should be falsifiable by pointing at code. If you cannot imagine the specific commit that violates it, it is not a rule.

**Not a rule:** "Payments should be reliable."
Nothing violates this. Nothing can.

**A rule:** "A payment instruction with the same idempotency key must never be executed twice."
You can point at the code that would break this. You can write a test for it. You can name the incident that happens when it fails.

The second one earns `BR-idempotent`. The first belongs in a strategy document where it will do less harm.

## Statement first, discussion after

Give each rule a `statement` field that is one sentence, present tense, and unconditional. That sentence is the contract; everything else is context.

```markdown
---
id: BR-idempotent
title: Idempotent execution
statement: A payment instruction with a given idempotency key executes at most once.
applies_to: [FEAT-payments, FEAT-retries]
---

Retries are inevitable -- clients time out, networks partition, and queues redeliver.
Without this guarantee, every one of those becomes a double charge...
```

The discipline of one sentence is doing real work. If you cannot state the rule in one sentence, you usually have two rules, or you have a decision rather than an invariant.

## Reference the features that carry them

`applies_to` turns the rulebook into a graph. Now you can ask which features are load-bearing for a given invariant, and -- more usefully -- which rules a feature must not break. When someone proposes deleting a feature, the rules pointing at it are the blast radius.

And because the reference is checked, deleting a feature while a rule still cites it fails the build.

## Rules outlive features

Features get replaced; the invariants they served usually do not. Keeping rules in their own collection with their own ids means the invariant survives three rewrites of the thing that implements it. That is the whole reason to separate them.

A rule that changes every quarter was a design note. Move it.
""")

POSTS["POST-naming-ids"] = ("""\
title: Naming artifact ids you will not regret
slug: naming-ids
date: 2026-04-08
summary: Ids are the most permanent thing you will write. A few conventions keep them from becoming a source of churn.
author: KeelSpec
category: practice
tags: [modelling, conventions]
related: [POST-dangling-references, POST-typed-artifacts]
reading_minutes: 3""", """
An id is a promise that other artifacts can depend on. Renaming one is a graph-wide operation. It is worth ten minutes of thought up front.

## Prefix by collection

`TERM-`, `BR-`, `FEAT-`, `ADR-`. KeelSpec enforces this with `id_prefix`, and the value is not bureaucratic: a bare id in a reference field tells a reader nothing, while `BR-idempotent` announces its collection. When you see it in a diff, in a log line, or in a support conversation, you know what kind of thing it is.

## Match the filename

The default is that `TERM-payment` lives in `TERM-payment.md`, and `PAC-011` enforces it. This sounds fussy until the first time you go looking for an artifact by id and find it instantly, or grep the repository for a reference and get both the definition and every citation in one result.

## Name the concept, not the wording

`TERM-payment` is good. `TERM-a-payment-is-an-instruction-to-move-money` is not, because the definition will be reworded and the id will not.

The id should survive rewrites of the artifact it names. Ask: if we completely rewrote this definition, would the id still be right? If not, it is describing prose rather than a concept.

## Avoid encoding hierarchy or ownership

`FEAT-payments-team-refunds-v2` bakes three things into a permanent string: a team, a grouping, and a version. All three will change. Teams reorganise, groupings get rethought, and v2 becomes v3.

Put those in fields, where they can change without a graph-wide rename. Ids should be flat and semantic.

## Do not number them

`BR-001` tells a reader nothing and makes the whole set impossible to reason about. It also creates a fake ordering, which invites questions about why `BR-014` comes before `BR-015` when nobody intended a sequence.

Use words. Ids are read far more often than they are typed.

## Renaming, when you must

Sometimes a concept genuinely changes name. The mechanics are the good news: change the id, change the filename, run the build, and let `PAC-020` list every artifact that needs updating. The rename is mechanical and complete, which is exactly the property free-form documents never had.
""")

for pid, (front, body) in POSTS.items():
    (OUT / f"{pid}.md").write_text(f"---\nid: {pid}\n{front}\n---\n{body}", encoding="utf-8", newline="\n")

print(f"wrote {len(POSTS)} posts")
