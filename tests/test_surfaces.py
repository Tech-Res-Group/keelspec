"""Tests for the editor and agent surfaces: the index, the watcher, the LSP, the MCP tools.

The rule these all serve: there is one judge. Every surface reports the engine's
verdict rather than forming its own, so the tests that matter most here are the ones
asserting a surface did *not* invent an opinion.
"""
from __future__ import annotations

import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastpdlc import lsp
from fastpdlc import mcp as mcp_tools
from fastpdlc.config import ArtifactType, Config, Reference
from fastpdlc.diagnostics import Report
from fastpdlc.engine import build, validate
from fastpdlc.index import ProductIndex, field_at, frontmatter_bounds, locate, token_at


def _write(root: pathlib.Path, rel: str, meta: dict, body: str = "body") -> None:
    p = root / "product" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\n" + yaml.safe_dump(meta, sort_keys=False) + "---\n" + body + "\n",
        encoding="utf-8",
    )


def _config() -> Config:
    """Two types that share an id space, and one that points at the other."""
    return Config(
        product_dir="product",
        output="build/b.json",
        types=[
            ArtifactType(
                name="features",
                dir="features",
                required=["id", "title"],
                fields=["title", "status", "rules"],
                enums={"status": ["idea", "shipped"]},
                references=[Reference(field="rules", to="rules")],
            ),
            ArtifactType(
                name="specs",
                dir="specs",
                required=["id", "title"],
                fields=["title", "feature"],
                references=[Reference(field="feature", to="features")],
            ),
            ArtifactType(
                name="rules",
                dir="rules",
                id_prefix="BR-",
                required=["id", "title"],
                fields=["title", "statement"],
            ),
        ],
    )


def _tree(root: pathlib.Path) -> Config:
    cfg = _config()
    # On disk too: the watcher and the CLI load the config by path, not by object.
    (root / "product.config.yaml").write_text(
        yaml.safe_dump(cfg.model_dump(mode="json")), encoding="utf-8")
    _write(root, "rules/BR-one.md", {"id": "BR-one", "title": "One", "statement": "Always one."})
    _write(root, "rules/BR-two.md", {"id": "BR-two", "title": "Two"})
    _write(root, "features/refunds.md",
           {"id": "refunds", "title": "Refunds", "status": "idea", "rules": ["BR-one"]})
    # Same id as the feature, different type -- the collision the index must survive.
    _write(root, "specs/refunds.md", {"id": "refunds", "title": "Refunds spec", "feature": "refunds"})
    build(cfg, root)
    return cfg


# ── the diagnostic carries its field ─────────────────────────────────────────
def test_report_add_is_backward_compatible_positionally():
    """A plugin written against the old three-argument signature keeps working."""
    r = Report()
    r.add("PAC-900", "something", "product/x.md")
    r.add("PAC-901", "advisory", "product/x.md", "warning")
    assert [(d.code, d.severity, d.field, d.value) for d in r.diagnostics] == [
        ("PAC-900", "error", "", ""),
        ("PAC-901", "warning", "", ""),
    ]


def test_engine_diagnostics_name_the_field_they_are_about(tmp_path):
    """The editor needs a range, and recovering it by matching prose is exactly what
    stable codes exist to stop consumers doing."""
    cfg = _tree(tmp_path)
    _write(tmp_path, "features/broken.md",
           {"id": "broken", "title": "B", "status": "nope", "rules": ["BR-ghost"]})
    build(cfg, tmp_path)
    found = {(d.code, d.field, d.value) for d in validate(cfg, tmp_path).diagnostics}
    assert ("PAC-030", "status", "nope") in found
    assert ("PAC-020", "rules", "BR-ghost") in found


# ── frontmatter scanning ─────────────────────────────────────────────────────
LINES = ["---", "id: FEAT-x", "rules:", "  - BR-one", "  - BR-two", "status: idea", "---",
         "prose mentioning status: shipped"]


def test_frontmatter_bounds_stop_at_the_closing_marker():
    assert frontmatter_bounds(LINES) == (1, 6)
    assert frontmatter_bounds(["no frontmatter here"]) == (0, 0)


def test_a_list_item_belongs_to_the_key_above_it():
    assert field_at(LINES, 3) == "rules"
    assert field_at(LINES, 4) == "rules"
    assert field_at(LINES, 5) == "status"


def test_prose_after_the_frontmatter_is_not_a_field():
    """`status:` in the body is text. Scanning the whole file would underline it."""
    assert field_at(LINES, 7) == ""


def test_token_at_spans_a_whole_id():
    assert token_at("  - CON-residency-pin", 8) == ("CON-residency-pin", 4, 21)
    assert token_at("  - CON-a", 1) == ("", 0, 0)  # on whitespace


def test_locate_finds_a_value_inside_a_block(tmp_path):
    _tree(tmp_path)
    loc = locate(tmp_path, "product/features/refunds.md", "rules", "BR-one")
    assert loc is not None
    line = (tmp_path / loc.path).read_text(encoding="utf-8").splitlines()[loc.line]
    assert line[loc.col:loc.end_col] == "BR-one"


def test_locate_falls_back_to_the_key_when_the_value_is_absent(tmp_path):
    _tree(tmp_path)
    loc = locate(tmp_path, "product/features/refunds.md", "status", "not-there")
    assert loc is not None and loc.col == 0


# ── the index ────────────────────────────────────────────────────────────────
def test_ids_are_unique_per_type_not_globally(tmp_path):
    """PAC-012 says duplicate *within a type*. An index keyed on the bare id silently
    merges a feature with the spec that shares its name."""
    cfg = _tree(tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    assert len(idx.artifacts) == 4
    assert {a.type_name for a in idx.find("refunds")} == {"features", "specs"}
    assert idx.get("refunds", "specs").title() == "Refunds spec"
    assert idx.get("refunds") is None  # ambiguous without a type, so it refuses to guess


def test_edges_are_typed_at_both_ends(tmp_path):
    cfg = _tree(tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    incoming = idx.references_to("BR-one")
    assert [(e.source_type, e.source_id, e.field) for e in incoming] == [
        ("features", "refunds", "rules")
    ]
    assert idx.references_to("refunds", "features")[0].source_type == "specs"


def test_allowed_values_distinguishes_enum_reference_and_free_text(tmp_path):
    cfg = _tree(tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    assert idx.allowed_values("features", "status") == ["idea", "shipped"]
    assert idx.allowed_values("features", "rules") == ["BR-one", "BR-two"]
    assert idx.allowed_values("features", "title") == []


def test_a_broken_file_does_not_blind_the_index(tmp_path):
    cfg = _tree(tmp_path)
    (tmp_path / "product" / "features" / "bad.md").write_text(
        "---\n: : not: yaml: [\n---\nbody\n", encoding="utf-8")
    idx = ProductIndex.build(cfg, tmp_path)
    assert idx.load_error  # recorded, not raised


def test_a_missing_required_field_still_gets_a_location(tmp_path):
    """PAC-001 is the one finding whose field is by definition not in the file."""
    cfg = _tree(tmp_path)
    _write(tmp_path, "features/untitled.md", {"id": "untitled"})
    build(cfg, tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    d = next(x for x in idx.diagnostics()
             if x.code == "PAC-001" and x.where.endswith("untitled.md"))
    loc = idx.locate_diagnostic(d)
    assert loc is not None and loc.line == 0


def test_the_index_does_not_validate_anything_itself(tmp_path):
    """One judge: the index's findings are the engine's, object for object."""
    cfg = _tree(tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    assert idx.diagnostics() == validate(cfg, tmp_path).diagnostics


# ── the language server's pure half ──────────────────────────────────────────
def _doc(root: pathlib.Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def test_completion_offers_only_values_that_would_validate(tmp_path):
    cfg = _tree(tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    rel = "product/features/refunds.md"
    text = _doc(tmp_path, rel)
    line = text.splitlines().index("status: idea")

    offers = lsp.completions_at(idx, rel, text, line, len("status: "))
    assert [c.label for c in offers] == ["idea", "shipped"]

    rules_line = text.splitlines().index("rules:")
    refs = lsp.completions_at(idx, rel, text, rules_line + 1, 4)
    assert [c.label for c in refs] == ["BR-one", "BR-two"]


def test_completion_in_key_position_omits_fields_already_present(tmp_path):
    cfg = _tree(tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    rel = "product/features/refunds.md"
    text = _doc(tmp_path, rel)
    line = text.splitlines().index("status: idea")
    offers = {c.label for c in lsp.completions_at(idx, rel, text, line, 0)}
    assert "title" not in offers  # already written
    assert "status" in offers  # the line the cursor is on is fair game


def test_completion_is_silent_outside_a_known_type(tmp_path):
    cfg = _tree(tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    assert lsp.completions_at(idx, "README.md", "---\nid: x\n---\n", 1, 4) == []


def test_hover_and_definition_follow_an_id(tmp_path):
    cfg = _tree(tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    rel = "product/features/refunds.md"
    text = _doc(tmp_path, rel)
    line = text.splitlines().index("- BR-one")
    card = lsp.hover_at(idx, text, line, 4)
    assert "BR-one" in card and "Always one." in card
    assert "Referenced by 1" in card

    locs = lsp.definition_at(idx, text, line, 4)
    assert [loc.path for loc in locs] == ["product/rules/BR-one.md"]


def test_definition_returns_both_artifacts_when_an_id_is_shared(tmp_path):
    cfg = _tree(tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    rel = "product/specs/refunds.md"
    text = _doc(tmp_path, rel)
    line = text.splitlines().index("feature: refunds")
    paths = {loc.path for loc in lsp.definition_at(idx, text, line, len("feature: ") + 2)}
    assert paths == {"product/features/refunds.md", "product/specs/refunds.md"}


def test_references_include_the_declaration_and_every_citation(tmp_path):
    cfg = _tree(tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    text = _doc(tmp_path, "product/rules/BR-one.md")
    line = text.splitlines().index("id: BR-one")
    paths = [loc.path for loc in lsp.references_at(idx, text, line, 4)]
    assert paths == ["product/rules/BR-one.md", "product/features/refunds.md"]


def test_clean_files_are_published_with_an_empty_list(tmp_path):
    """An editor keeps the underlines it was last given, so a fixed file has to be
    told it is clean. Only the sender knows it went quiet."""
    cfg = _tree(tmp_path)
    _write(tmp_path, "features/broken.md", {"id": "broken", "title": "B", "rules": ["BR-ghost"]})
    build(cfg, tmp_path)
    grouped = lsp.diagnostics_by_file(ProductIndex.build(cfg, tmp_path))

    assert "product/features/refunds.md" in grouped
    assert grouped["product/features/refunds.md"] == []
    codes = [d.code for _, d in grouped["product/features/broken.md"]]
    assert codes == ["PAC-020"]


def test_tree_level_findings_are_not_hung_on_a_file(tmp_path):
    """PAC-060 is true of the repository, not of any line in it."""
    cfg = _tree(tmp_path)
    (tmp_path / "build" / "b.json").unlink()  # the bundle is now missing
    idx = ProductIndex.build(cfg, tmp_path)
    assert any(d.code == "PAC-060" for d in idx.diagnostics())
    assert all(
        d.code != "PAC-060" for found in lsp.diagnostics_by_file(idx).values() for _, d in found
    )


def test_symbols_search_matches_id_or_title(tmp_path):
    cfg = _tree(tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    assert {s[0] for s in lsp.symbols(idx, "BR-")} == {"BR-one", "BR-two"}
    assert {s[0] for s in lsp.symbols(idx, "refunds spec")} == {"refunds"}


# ── the MCP tool bodies ──────────────────────────────────────────────────────
def test_schema_tool_describes_every_type(tmp_path):
    cfg = _tree(tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    by_name = {t["type"]: t for t in mcp_tools.schema(idx)}
    assert by_name["features"]["enums"]["status"] == ["idea", "shipped"]
    assert by_name["features"]["references"] == [
        {"field": "rules", "must_resolve_to": "rules"}
    ]
    assert by_name["rules"]["id_prefix"] == "BR-"
    assert by_name["rules"]["count"] == 2


def test_allowed_values_tool_labels_the_kind_of_field(tmp_path):
    cfg = _tree(tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    assert mcp_tools.allowed_values(idx, "features", "status")["kind"] == "enum"
    ref = mcp_tools.allowed_values(idx, "features", "rules")
    assert ref["kind"] == "reference" and ref["must_resolve_to"] == "rules"
    assert mcp_tools.allowed_values(idx, "features", "title")["closed"] is False


def test_get_artifact_reports_both_directions(tmp_path):
    cfg = _tree(tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    got = mcp_tools.get_artifact(idx, "BR-one")
    assert got["referenced_by"] == [
        {"source": "refunds", "source_type": "features", "field": "rules"}
    ]
    shared = mcp_tools.get_artifact(idx, "refunds")
    assert len(shared["matches"]) == 2
    assert mcp_tools.get_artifact(idx, "nope")["error"]


def test_validate_tool_reports_the_gate_verbatim(tmp_path):
    cfg = _tree(tmp_path)
    idx = ProductIndex.build(cfg, tmp_path)
    assert mcp_tools.validate(idx)["result"] == "pass"

    _write(tmp_path, "features/broken.md", {"id": "broken", "title": "B", "rules": ["BR-ghost"]})
    build(cfg, tmp_path)
    out = mcp_tools.validate(ProductIndex.build(cfg, tmp_path))
    assert out["result"] == "fail"
    assert any(f["code"] == "PAC-020" and f["value"] == "BR-ghost" for f in out["findings"])


# ── the watcher ──────────────────────────────────────────────────────────────
def test_watch_validates_once_then_stays_quiet(tmp_path, capsys):
    from fastpdlc.watch import watch

    _tree(tmp_path)
    assert watch(str(tmp_path / "product.config.yaml"), tmp_path, ticks=3) == 0
    out = capsys.readouterr().out
    assert out.count("clean") == 1  # three ticks, one unchanged tree, one report


def test_watch_is_not_a_gate(tmp_path, capsys):
    """A red tree you are mid-fix must not kill the terminal you are fixing it in."""
    from fastpdlc.watch import watch

    cfg = _tree(tmp_path)
    _write(tmp_path, "features/broken.md", {"id": "broken", "title": "B", "rules": ["BR-ghost"]})
    build(cfg, tmp_path)
    assert watch(str(tmp_path / "product.config.yaml"), tmp_path, ticks=1) == 0
    assert "PAC-020" in capsys.readouterr().out


def test_watch_survives_a_config_it_cannot_load(tmp_path, capsys):
    from fastpdlc.watch import watch

    _tree(tmp_path)
    (tmp_path / "product.config.yaml").write_text("types: [oh no\n", encoding="utf-8")
    assert watch(str(tmp_path / "product.config.yaml"), tmp_path, ticks=2) == 0
    assert "cannot load" in capsys.readouterr().out


# ── the CLI surface ──────────────────────────────────────────────────────────
def test_cli_rejects_watch_with_json(tmp_path, capsys):
    """A JSON document per tick is not a format anything consumes; say so rather than
    emitting a stream nobody can parse."""
    from fastpdlc.cli import main

    _tree(tmp_path)
    assert main(["-C", str(tmp_path), "validate", "--watch", "--json"]) == 2
    assert "mutually exclusive" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("command", "module", "extra"),
    [("lsp", "pygls", "fastpdlc[lsp]"), ("mcp", "mcp", "fastpdlc[mcp]")],
)
def test_optional_surfaces_explain_their_extra(tmp_path, capsys, command, module, extra):
    """Without the dependency the command must say what to install -- not traceback,
    and not silently start something that never speaks."""
    try:
        __import__(module)
    except ImportError:
        pass
    else:
        pytest.skip(f"{module} is installed; this asserts the missing-dependency path")

    from fastpdlc.cli import main

    _tree(tmp_path)
    assert main(["-C", str(tmp_path), command]) == 2
    assert extra in capsys.readouterr().err
