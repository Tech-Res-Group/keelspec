---
id: TERM-artifact
term: Artifact
definition: >-
  One record in the graph: a markdown file with YAML frontmatter, belonging to a
  type declared in product.config.yaml, identified by an id that is unique within
  that type.
aka: [record]
see_also: [TERM-bundle, TERM-diagnostic-code]
---
An artifact is identified by its type *and* its id, not by its id alone. Two
types may legitimately use the same id — a spec and the feature it details
usually do — and treating the id as globally unique is the mistake KDR-0003 was
written about.

The frontmatter is the data; the body is prose for a human. The engine validates
the frontmatter and carries the body through to the bundle untouched. Nothing
enforces that the body says anything, which is deliberate: a rule that is true and
unexplained is still a rule, and forcing a justification field produces
justifications rather than reasons.
