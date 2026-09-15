---
title: Reviewing product changes in pull requests — KeelSpec
description: When intent lives in the repository, product decisions get the same review rigour as code. That changes the conversation more than the tooling does.
url: https://keelspec.com/blog/review-culture.html
---
# Reviewing product changes in pull requests

When intent lives in the repository, product decisions get the same review rigour as code. That changes the conversation more than the tooling does.

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

### Related

- [Anatomy of a product CI gate](/blog/ci-gate-anatomy.html)
- [Commit the generated bundle](/blog/committing-generated-bundles.html)

## Get the next one by email.

Short notes on product-as-code,
 new diagnostic codes, and what breaks in real repositories. Twice a week, unsubscribe in one click.
