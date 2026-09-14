---
id: POST-committing-generated-bundles
title: Commit the generated bundle
slug: committing-generated-bundles
date: 2026-03-25
summary: Build artifacts usually do not belong in git. This one does, and the reason is that it turns invisible drift into a reviewable diff.
author: KeelSpec
category: practice
tags: [ci, workflow]
related: [POST-the-staleness-gate, POST-review-culture]
reading_minutes: 4
---

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
