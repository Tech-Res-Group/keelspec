---
id: BR-one-index-behind-every-surface
title: Every surface answers from one resolved index
governed_by: KDR-0003
statement: >-
  The CLI, the language server, the MCP server and watch mode all resolve the
  graph through keelspec/index.py. No surface traverses the tree itself, and no
  surface may answer a question about the graph that the index could have
  answered differently.
invariant: >-
  Artifacts are keyed by (type_name, id), never by id alone, and every edge
  records the source type, source id, field, target type and target id. A lookup
  by bare id returns a list, because a bare id does not identify an artifact.
enforced_by:
  - tests/test_surfaces.py::test_ids_are_unique_per_type_not_globally
  - tests/test_surfaces.py::test_edges_are_typed_at_both_ends
  - tests/test_surfaces.py::test_definition_returns_both_artifacts_when_an_id_is_shared
  - tests/test_surfaces.py::test_the_index_does_not_validate_anything_itself
---
The failure this prevents is silent. When the index was keyed by bare id, a tree
of 85 artifacts resolved to 62 — every spec that shared an id with the feature it
details was overwritten by it. Nothing errored. The count was simply lower than
it should have been, on a number nobody had a reason to check, and the only
reason it surfaced was that the CLI still did its own loading and disagreed.

The last of the four tests is the one that ages worst if it goes. The index
resolves; it does not judge. A surface that wants a diagnostic asks the
validator. The moment the index starts deciding what is wrong, two answers to
"is this tree valid" exist again, which is the whole thing KDR-0003 was written
to stop.
