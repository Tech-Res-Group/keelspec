---
id: POST-enums-and-lifecycles
title: Modelling lifecycles with enums
slug: enums-and-lifecycles
date: 2026-05-20
summary: Four spellings of in-progress is not a naming problem. It is a missing constraint, and PAC-030 is the fix.
author: KeelSpec
category: practice
tags: [modelling, schema]
related: [POST-business-rules, POST-typed-artifacts]
reading_minutes: 3
---

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
