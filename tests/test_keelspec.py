"""Tests for the KeelSpec engine: schema/id/reference/enum/staleness + the plugin API."""
from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from keelspec import build, register, render_bundle, validate
from keelspec.config import ArtifactType, Config, Reference
from keelspec.plugin import Registry


def _write(root: pathlib.Path, rel: str, meta: dict, body: str = "body") -> None:
    p = root / "product" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\n" + yaml.safe_dump(meta, sort_keys=False) + "---\n" + body + "\n", encoding="utf-8")


def _config() -> Config:
    return Config(
        product_dir="product",
        output="build/b.json",
        types=[
            ArtifactType(
                name="terms",
                dir="terms",
                id_prefix="TERM-",
                required=["id", "term"],
                fields=["term", "kind", "see_also"],
                enums={"kind": ["money", "ops"]},
                references=[Reference(field="see_also", to="terms")],
            )
        ],
    )


def _codes(report) -> set[str]:
    return {d.code for d in report.diagnostics}


def _fresh(tmp_path, cfg) -> None:
    build(cfg, tmp_path)  # so PAC-060 (staleness) doesn't fire on unrelated tests


def test_valid_tree_passes(tmp_path):
    cfg = _config()
    _write(tmp_path, "terms/TERM-a.md", {"id": "TERM-a", "term": "A", "kind": "money"})
    _fresh(tmp_path, cfg)
    assert validate(cfg, tmp_path).ok


def test_missing_required_field_pac001(tmp_path):
    cfg = _config()
    _write(tmp_path, "terms/TERM-a.md", {"id": "TERM-a"})  # no `term`
    _fresh(tmp_path, cfg)
    assert "PAC-001" in _codes(validate(cfg, tmp_path))


def test_bad_prefix_pac010(tmp_path):
    cfg = _config()
    _write(tmp_path, "terms/BAD-a.md", {"id": "BAD-a", "term": "A"})
    _fresh(tmp_path, cfg)
    assert "PAC-010" in _codes(validate(cfg, tmp_path))


def test_filename_mismatch_pac011(tmp_path):
    cfg = _config()
    _write(tmp_path, "terms/TERM-wrong.md", {"id": "TERM-a", "term": "A"})
    _fresh(tmp_path, cfg)
    assert "PAC-011" in _codes(validate(cfg, tmp_path))


def test_unresolved_reference_pac020(tmp_path):
    cfg = _config()
    _write(tmp_path, "terms/TERM-a.md", {"id": "TERM-a", "term": "A", "see_also": ["TERM-ghost"]})
    _fresh(tmp_path, cfg)
    assert "PAC-020" in _codes(validate(cfg, tmp_path))


def test_enum_violation_pac030(tmp_path):
    cfg = _config()
    _write(tmp_path, "terms/TERM-a.md", {"id": "TERM-a", "term": "A", "kind": "banana"})
    _fresh(tmp_path, cfg)
    assert "PAC-030" in _codes(validate(cfg, tmp_path))


def test_stale_bundle_pac060(tmp_path):
    cfg = _config()
    _write(tmp_path, "terms/TERM-a.md", {"id": "TERM-a", "term": "A"})
    # never built -> missing/stale
    assert "PAC-060" in _codes(validate(cfg, tmp_path))


def test_build_is_deterministic(tmp_path):
    cfg = _config()
    _write(tmp_path, "terms/TERM-a.md", {"id": "TERM-a", "term": "A"})
    assert render_bundle(cfg, tmp_path) == render_bundle(cfg, tmp_path)


# ── plugin system ────────────────────────────────────────────────────────────
def test_plugin_validator_and_transformer_and_output(tmp_path):
    cfg = _config()
    _write(tmp_path, "terms/TERM-a.md", {"id": "TERM-a", "term": "A"})

    register("PAC-900", "custom: term has no body")
    reg = Registry()

    @reg.validator
    def bodies_present(bundle, config, root, report):
        for rec in bundle["terms"]:
            if not rec["body"]:
                report.add("PAC-900", "term has no body", rec["_file"])

    @reg.bundle_transformer
    def add_count(bundle, config, root):
        bundle["term_count"] = len(bundle["terms"])

    reg.extra_output(
        "build/catalogue.json",
        lambda bundle, config, root: json.dumps({"n": bundle["term_count"]}) + "\n",
    )

    written = build(cfg, tmp_path, reg)
    assert (tmp_path / "build" / "catalogue.json").exists()
    assert len(written) == 2  # main bundle + extra output
    # the transformer field is in the bundle
    assert json.loads((tmp_path / "build" / "b.json").read_text())["term_count"] == 1
    # validate is clean (bodies present, outputs fresh)
    assert validate(cfg, tmp_path, reg).ok

    # a body-less term trips the custom validator; a hand-edited catalogue trips PAC-060
    _write(tmp_path, "terms/TERM-b.md", {"id": "TERM-b", "term": "B"}, body="")
    build(cfg, tmp_path, reg)
    (tmp_path / "build" / "catalogue.json").write_text("stale\n")
    codes = _codes(validate(cfg, tmp_path, reg))
    assert "PAC-900" in codes and "PAC-060" in codes


def test_dates_in_frontmatter_serialize_to_iso(tmp_path):
    """YAML turns an unquoted 2026-02-04 into datetime.date; the bundle must still
    build, emitting ISO-8601 rather than blowing up in json.dumps."""
    (tmp_path / "product" / "posts").mkdir(parents=True)
    (tmp_path / "product" / "posts" / "POST-hello.md").write_text(
        "---\nid: POST-hello\ntitle: Hello\ndate: 2026-02-04\n---\nBody.\n",
        encoding="utf-8",
    )
    (tmp_path / "product.config.yaml").write_text(
        "product_dir: product\n"
        "output: build/out.json\n"
        "types:\n"
        "  - name: posts\n"
        "    dir: posts\n"
        "    id_prefix: 'POST-'\n"
        "    required: [id, title, date]\n"
        "    fields: [title, date]\n",
        encoding="utf-8",
    )
    from keelspec import engine
    from keelspec.config import load_config

    config = load_config(str(tmp_path / "product.config.yaml"))
    engine.build(config, str(tmp_path))
    bundle = json.loads((tmp_path / "build" / "out.json").read_text(encoding="utf-8"))
    assert bundle["posts"][0]["date"] == "2026-02-04"
    assert engine.validate(config, str(tmp_path)).ok


def _tiny_project(tmp_path):
    (tmp_path / "product" / "terms").mkdir(parents=True)
    (tmp_path / "product" / "terms" / "TERM-payment.md").write_text(
        "---\nid: TERM-payment\nterm: Payment\ndefinition: Moving money.\n---\nBody.\n",
        encoding="utf-8",
    )
    (tmp_path / "product.config.yaml").write_text(
        "product_dir: product\n"
        "output: build/out.json\n"
        "types:\n"
        "  - name: terms\n"
        "    dir: terms\n"
        "    id_prefix: 'TERM-'\n"
        "    required: [id, term, definition]\n"
        "    fields: [term, definition]\n",
        encoding="utf-8",
    )
    from keelspec.config import load_config
    return load_config(str(tmp_path / "product.config.yaml"))


def test_evidence_record_is_content_addressed(tmp_path):
    """Every artifact and the bundle carry a digest, so a record can be verified by
    recomputation rather than by trusting whoever produced it."""
    import hashlib

    from keelspec import engine, evidence

    config = _tiny_project(tmp_path)
    engine.build(config, str(tmp_path))
    record = evidence.build_record(config, str(tmp_path))

    assert record["schema"] == "keelspec-evidence/1"
    assert record["result"] == "pass"
    assert record["counts"] == {"terms": 1}

    artifact = record["artifacts"]["terms"][0]
    on_disk = (tmp_path / artifact["file"]).read_bytes()
    assert artifact["sha256"] == hashlib.sha256(on_disk).hexdigest()

    bundle_bytes = (tmp_path / "build" / "out.json").read_bytes()
    assert record["bundle"]["sha256"] == hashlib.sha256(bundle_bytes).hexdigest()
    assert record["bundle"]["matches_sources"] is True


def test_evidence_reports_staleness_and_failure(tmp_path):
    """A record of a failing run is still a valid record -- it just says so."""
    from keelspec import engine, evidence

    config = _tiny_project(tmp_path)
    engine.build(config, str(tmp_path))

    # edit a source without rebuilding: the classic drift
    (tmp_path / "product" / "terms" / "TERM-payment.md").write_text(
        "---\nid: TERM-payment\nterm: Payment\ndefinition: Changed.\n---\nBody.\n",
        encoding="utf-8",
    )
    record = evidence.build_record(config, str(tmp_path))

    assert record["result"] == "fail"
    assert record["bundle"]["matches_sources"] is False
    assert any(f["code"] == "PAC-060" for f in record["findings"])


def test_evidence_is_reproducible_apart_from_the_timestamp(tmp_path):
    """Two runs on one commit must agree; that is what makes historical evidence
    a checkout away rather than a feature."""
    from keelspec import engine, evidence

    config = _tiny_project(tmp_path)
    engine.build(config, str(tmp_path))

    first = evidence.build_record(config, str(tmp_path))
    second = evidence.build_record(config, str(tmp_path))
    first.pop("generated_at")
    second.pop("generated_at")
    assert evidence.render(first) == evidence.render(second)


def test_cli_surface_manifest_is_current():
    """site/api/cli_surface.json is generated from argparse and consumed by the
    newsletter generator. If it drifts, the newsletter starts rejecting true
    statements about our own CLI -- so gate it the way we gate everything else.

    This is PAC-060 applied to our own tooling: regenerate with
    `python site/tools/gen_cli_surface.py` and commit the result.
    """
    import importlib.util

    repo = pathlib.Path(__file__).resolve().parents[1]
    gen = repo / "site" / "tools" / "gen_cli_surface.py"
    committed = repo / "site" / "api" / "cli_surface.json"
    if not gen.exists() or not committed.exists():
        pytest.skip("site tooling not present")

    spec = importlib.util.spec_from_file_location("gen_cli_surface", gen)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    expected = module.render(module.build_surface())
    actual = committed.read_text(encoding="utf-8")
    assert actual == expected, (
        "cli_surface.json is stale -- run: python site/tools/gen_cli_surface.py"
    )


# ── the agent-built lifecycle ────────────────────────────────────────────────
def _orch(**kw):
    from keelspec import orchestration
    return orchestration, kw


def test_pipeline_runs_the_stations_in_order():
    from keelspec.orchestration import Orchestrator, StubRunner

    runner = StubRunner()
    report = Orchestrator(runner).run("FEAT-refunds")

    assert report.status == "proposed"
    assert [s.station for s in report.steps] == [
        "ST-01", "ST-02", "ST-03", "ST-04", "ST-04b", "ST-05"]
    # all four lenses ran, and none of them shipped an opinion it did not have
    assert [v.lens for v in report.verdicts] == [
        "correctness", "coverage", "security", "reproduce"]
    assert report.repair_rounds == 0


def test_disambiguate_blocks_before_design():
    """Building the wrong thing correctly is the expensive failure: an open question
    must stop the line before the Architect starts."""
    from keelspec.orchestration import Orchestrator, StubRunner

    questions = [{"id": "q1", "dimension": "refund window start",
                  "question": "From authorization, settlement or delivery?"}]
    report = Orchestrator(StubRunner(questions=questions)).run("FEAT-refunds")

    assert report.status == "blocked"
    assert report.disambiguation == questions
    stations = [s.station for s in report.steps]
    assert stations == ["ST-01", "ST-02"]          # Design never ran
    assert "ST-03" not in stations


def test_advisory_gate_records_questions_but_does_not_block():
    """block_on_unresolved=False is the autonomous run: open questions are still
    recorded on the report, but the line proceeds to build rather than stopping —
    the PR's gates and the human merge become the judge."""
    from keelspec.orchestration import Orchestrator, StubRunner

    questions = [{"id": "q1", "dimension": "refund window start",
                  "question": "From authorization, settlement or delivery?"}]
    report = Orchestrator(StubRunner(questions=questions)).run(
        "FEAT-refunds", block_on_unresolved=False)

    assert report.status == "proposed"                 # it built, did not block
    assert report.disambiguation == questions          # but the questions ride along
    stations = [s.station for s in report.steps]
    assert "ST-03" in stations and "ST-04" in stations  # Design + Develop ran
    assert any("advisory gate" in n for n in report.notes)


def test_blocking_gate_is_the_default():
    """The safe default is unchanged: without opting in, an open question blocks."""
    from keelspec.orchestration import Orchestrator, StubRunner

    questions = [{"id": "q1", "dimension": "d", "question": "?"}]
    report = Orchestrator(StubRunner(questions=questions)).run("FEAT-refunds")
    assert report.status == "blocked"                  # default still blocks
    assert "ST-03" not in [s.station for s in report.steps]


def test_resolved_questions_let_the_line_continue():
    from keelspec.orchestration import Orchestrator, StubRunner

    questions = [{"id": "q1", "dimension": "refund window start", "question": "?"}]
    report = Orchestrator(
        StubRunner(questions=questions),
        resolutions={"q1": "from settlement"},
    ).run("FEAT-refunds")

    assert report.status == "proposed"
    assert "ST-03" in [s.station for s in report.steps]


def test_a_blocking_verdict_triggers_bounded_repair():
    from keelspec.orchestration import Orchestrator, StubRunner

    refuting = {"security": {"lens": "security", "refuted": True, "severity": "blocker",
                             "reason": "no authz on the money path",
                             "failing_case": "unauthenticated POST /refunds"}}
    report = Orchestrator(StubRunner(verdicts=refuting)).run("FEAT-refunds")

    assert report.status == "refuted"
    assert report.repair_rounds == 2                       # the bound, not forever
    assert [v.lens for v in report.blocking] == ["security"]
    assert "ST-04" in [s.station for s in report.steps]     # repair ran on the developer


def test_minor_findings_do_not_block():
    """A gate that fires on nitpicks gets bypassed, and a bypassed gate is worse
    than none."""
    from keelspec.orchestration import Orchestrator, StubRunner

    nitpick = {"coverage": {"lens": "coverage", "refuted": True, "severity": "minor",
                            "reason": "could add one more edge case", "failing_case": ""}}
    report = Orchestrator(StubRunner(verdicts=nitpick)).run("FEAT-refunds")

    assert report.status == "proposed"
    assert report.blocking == []
    assert report.repair_rounds == 0


def test_a_failed_lens_abstains_rather_than_blocking():
    """An unreachable critic must never take down the line."""
    from keelspec.orchestration import VERDICT_SCHEMA, Orchestrator

    class Flaky:
        def run(self, station, prompt, schema=None):
            if schema is VERDICT_SCHEMA and '"security"' in prompt:
                raise RuntimeError("provider unreachable")
            if schema is VERDICT_SCHEMA:
                return {"lens": "x", "refuted": False, "severity": "none", "reason": "ok"}
            return {"questions": [], "approach": "a", "files": [], "criteria_to_tests": [],
                    "files_changed": [], "diff_summary": "d",
                    "tests_added": [], "tests_passed": True, "coverage_notes": "c"}

    report = Orchestrator(Flaky()).run("FEAT-refunds")
    security = next(v for v in report.verdicts if v.lens == "security")
    assert security.refuted is False
    assert "inconclusive" in security.reason
    assert report.status == "proposed"


def test_the_orchestrator_cannot_merge_anything():
    """Its terminal state is a report. Autonomy stops where the stakes rise."""
    from keelspec import orchestration
    from keelspec.orchestration import Orchestrator, StubRunner

    report = Orchestrator(StubRunner()).run("FEAT-refunds")
    assert report.status in {"proposed", "refuted", "blocked", "error"}
    # no station on the line past the gate is an agent
    for sid in ("ST-07", "ST-08", "ST-09", "ST-10"):
        assert orchestration.BY_ID[sid].kind != orchestration.AGENT
    assert orchestration.BY_ID["ST-09"].kind == orchestration.HUMAN


# ── the coding sandbox ───────────────────────────────────────────────────────
def test_sandbox_refuses_escape_attempts(tmp_path):
    """A model is driving this. Containment is checked after resolution, so `..`,
    absolute paths and symlinks are refused rather than sanitised."""
    from keelspec.coding import PathOutsideRoot, Sandbox

    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("do not read me\n", encoding="utf-8")

    box = Sandbox(root, write=True)
    assert box.read_file("src/a.py") == "x = 1\n"

    for escape in ["../secret.txt", "src/../../secret.txt", "src/../..",
                   str(tmp_path / "secret.txt")]:
        with pytest.raises(PathOutsideRoot):
            box.resolve(escape)


def test_sandbox_dry_run_records_but_does_not_write(tmp_path):
    from keelspec.coding import Sandbox

    root = tmp_path / "project"
    root.mkdir()
    box = Sandbox(root, write=False)
    box.write_file("new.py", "print('hi')\n")

    assert box.written == ["new.py"]
    assert not (root / "new.py").exists()          # proposed, not applied


def test_sandbox_writes_when_enabled(tmp_path):
    from keelspec.coding import Sandbox

    root = tmp_path / "project"
    root.mkdir()
    box = Sandbox(root, write=True)
    box.write_file("pkg/new.py", "print('hi')\n")

    assert (root / "pkg" / "new.py").read_text(encoding="utf-8") == "print('hi')\n"


# ── the cross-provider adversary ─────────────────────────────────────────────
def test_cross_provider_lens_is_skipped_without_a_key(monkeypatch):
    from keelspec.runners import CROSS_PROVIDER_LENS, CrossProviderLens

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    lens = CrossProviderLens()
    assert lens.enabled is False

    verdict = lens.verdict("context")
    assert verdict["lens"] == CROSS_PROVIDER_LENS
    assert verdict["refuted"] is False              # abstains, never blocks


def test_cross_provider_lens_abstains_when_the_call_fails(monkeypatch):
    """A diverse critic that cannot be reached must not take down the line."""
    import urllib.request

    from keelspec.runners import CrossProviderLens

    def boom(*a, **kw):
        raise OSError("network unreachable")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    lens = CrossProviderLens(api_key="test-key")
    assert lens.enabled is True

    verdict = lens.verdict("context")
    assert verdict["refuted"] is False
    assert "inconclusive" in verdict["reason"]


def test_cross_provider_verdict_joins_the_refute_logic():
    """When the diverse critic refutes, it blocks exactly like a native lens."""
    from keelspec.orchestration import Orchestrator, StubRunner

    def refusing_lens(context: str) -> dict:
        return {"lens": "cross-provider(openrouter)", "refuted": True,
                "severity": "blocker", "reason": "authz missing on the money path",
                "failing_case": "unauthenticated refund"}

    report = Orchestrator(StubRunner(), extra_lens=refusing_lens,
                          max_repair=1).run("FEAT-refunds")

    assert len(report.verdicts) == 5                      # four native + one diverse
    assert report.status == "refuted"
    assert report.repair_rounds == 1
    assert [v.lens for v in report.blocking] == ["cross-provider(openrouter)"]


# ── the human gate as a file ─────────────────────────────────────────────────
def test_disambiguation_file_is_the_two_phase_gate(tmp_path):
    """pharthing parks these in a console; a library cannot assume a service, so the
    same gate is a file. Run 1 blocks and writes it, a human answers, run 2 proceeds."""
    from keelspec.orchestration import Orchestrator, StubRunner, read_resolutions, write_questions

    questions = [{"id": "q1", "dimension": "refund window start", "question": "?"}]

    first = Orchestrator(StubRunner(questions=questions)).run("FEAT-refunds")
    assert first.status == "blocked"

    path = write_questions(tmp_path, "FEAT-refunds", first.disambiguation)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "pending"
    assert payload["questions"][0]["answer"] == ""        # waiting on a person

    payload["questions"][0]["answer"] = "from settlement"
    path.write_text(json.dumps(payload), encoding="utf-8")

    second = Orchestrator(StubRunner(questions=questions),
                          resolutions=read_resolutions(tmp_path, "FEAT-refunds")
                          ).run("FEAT-refunds")
    assert second.status == "proposed"
    assert "ST-03" in [s.station for s in second.steps]


# ── the plugin loader: the extension point everything else hangs off ─────────
def _plugin_project(tmp_path):
    (tmp_path / "product" / "features").mkdir(parents=True)
    (tmp_path / "product" / "features" / "FEAT-refunds.md").write_text(
        "---\nid: FEAT-refunds\ntitle: Refunds\ncode: [src/refunds.py, src/gone.py]\n---\nBody.\n",
        encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "refunds.py").write_text("# real\n", encoding="utf-8")
    (tmp_path / "product.config.yaml").write_text(
        "product_dir: product\n"
        "output: build/out.json\n"
        "types:\n"
        "  - name: features\n"
        "    dir: features\n"
        "    id_prefix: 'FEAT-'\n"
        "    required: [id, title]\n"
        "    fields: [title, code]\n",
        encoding="utf-8")
    from keelspec.config import load_config
    return load_config(str(tmp_path / "product.config.yaml"))


PLUGIN_SRC = r'''
from keelspec import register

def register_codes():
    register("PAC-900", "links.code path does not exist on disk")

def register(reg):
    from keelspec.diagnostics import register as reg_code
    reg_code("PAC-900", "links.code path does not exist on disk")

    @reg.validator
    def code_paths_exist(bundle, config, root, report):
        for f in bundle["features"]:
            for path in f.get("code") or []:
                if not (root / path).exists():
                    report.add("PAC-900", f"missing {path}", f["_file"])

    @reg.bundle_transformer
    def stamp(bundle, config, root):
        bundle["_stamped"] = True

    reg.extra_output("build/catalogue.json", lambda bundle, config, root: "{}\n")
'''


def test_plugin_loads_from_a_file_and_its_validator_runs(tmp_path):
    """The documented plugin path -- keelspec -p product_hooks.py -- and the exact
    PAC-900 example from the README."""
    from keelspec import engine
    from keelspec.plugin import load_plugin

    config = _plugin_project(tmp_path)
    (tmp_path / "hooks.py").write_text(PLUGIN_SRC, encoding="utf-8")
    registry = load_plugin(str(tmp_path / "hooks.py"))

    assert len(registry.validators) == 1
    assert len(registry.bundle_transformers) == 1
    assert len(registry.extra_outputs) == 1

    engine.build(config, str(tmp_path), registry)
    report = engine.validate(config, str(tmp_path), registry)

    codes = [d.code for d in report.diagnostics]
    assert "PAC-900" in codes
    finding = next(d for d in report.diagnostics if d.code == "PAC-900")
    assert "src/gone.py" in finding.message
    assert "src/refunds.py" not in finding.message      # the one that exists is fine


def test_plugin_bundle_transformer_reaches_the_committed_bundle(tmp_path):
    from keelspec import engine
    from keelspec.plugin import load_plugin

    config = _plugin_project(tmp_path)
    (tmp_path / "hooks.py").write_text(PLUGIN_SRC, encoding="utf-8")
    registry = load_plugin(str(tmp_path / "hooks.py"))

    engine.build(config, str(tmp_path), registry)
    bundle = json.loads((tmp_path / "build" / "out.json").read_text(encoding="utf-8"))
    assert bundle["_stamped"] is True


def test_plugin_extra_outputs_are_staleness_gated(tmp_path):
    """A generated file nothing verifies is a generated file that will fall behind.
    Plugin outputs get the same PAC-060 treatment as the bundle."""
    from keelspec import engine
    from keelspec.plugin import load_plugin

    config = _plugin_project(tmp_path)
    (tmp_path / "hooks.py").write_text(PLUGIN_SRC, encoding="utf-8")
    registry = load_plugin(str(tmp_path / "hooks.py"))

    engine.build(config, str(tmp_path), registry)
    assert (tmp_path / "build" / "catalogue.json").exists()

    (tmp_path / "build" / "catalogue.json").write_text("tampered\n", encoding="utf-8")
    report = engine.validate(config, str(tmp_path), registry)
    stale = [d for d in report.errors if d.code == "PAC-060" and "catalogue" in d.message]
    assert stale, "a tampered plugin output must fail PAC-060"


def test_no_plugin_yields_an_empty_registry():
    from keelspec.plugin import load_plugin
    for spec in (None, ""):
        reg = load_plugin(spec)
        assert reg.validators == [] and reg.bundle_transformers == []


def test_a_plugin_without_register_fails_loudly(tmp_path):
    """Silently ignoring a plugin that does not register anything would let a
    project believe its checks are running when they are not."""
    from keelspec.plugin import load_plugin

    (tmp_path / "empty.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        load_plugin(str(tmp_path / "empty.py"))
    assert "register" in str(exc.value)


# ── the CLI: exit codes are the contract ────────────────────────────────────
def _cli_project(tmp_path):
    (tmp_path / "product" / "terms").mkdir(parents=True)
    (tmp_path / "product" / "terms" / "TERM-payment.md").write_text(
        "---\nid: TERM-payment\nterm: Payment\ndefinition: Moving money.\n"
        "see_also: [TERM-ledger]\n---\nBody.\n", encoding="utf-8")
    (tmp_path / "product" / "terms" / "TERM-ledger.md").write_text(
        "---\nid: TERM-ledger\nterm: Ledger\ndefinition: The record.\n---\nBody.\n",
        encoding="utf-8")
    (tmp_path / "product.config.yaml").write_text(
        "product_dir: product\n"
        "output: build/out.json\n"
        "types:\n"
        "  - name: terms\n"
        "    dir: terms\n"
        "    id_prefix: 'TERM-'\n"
        "    required: [id, term, definition]\n"
        "    fields: [term, definition, see_also]\n"
        "    references:\n"
        "      - field: see_also\n"
        "        to: terms\n",
        encoding="utf-8")
    return tmp_path


def test_cli_build_then_validate_exits_zero(tmp_path, capsys):
    from keelspec.cli import main

    root = _cli_project(tmp_path)
    assert main(["-C", str(root), "build"]) == 0
    assert (root / "build" / "out.json").exists()
    assert main(["-C", str(root), "validate"]) == 0

    out = capsys.readouterr().out
    assert "terms 2" in out
    assert "0 error(s)" in out


def test_cli_validate_exits_nonzero_on_a_dangling_reference(tmp_path, capsys):
    """The exit code IS the gate. If this ever returns 0 with errors present, every
    CI job using KeelSpec goes green while broken."""
    from keelspec.cli import main

    root = _cli_project(tmp_path)
    main(["-C", str(root), "build"])
    (root / "product" / "terms" / "TERM-ledger.md").unlink()      # break the graph

    assert main(["-C", str(root), "validate"]) == 1
    out = capsys.readouterr().out
    assert "PAC-020" in out
    assert "PAC-060" in out            # the bundle is now stale too


def test_cli_validate_exits_nonzero_when_the_bundle_is_missing(tmp_path):
    from keelspec.cli import main

    root = _cli_project(tmp_path)
    assert main(["-C", str(root), "validate"]) == 1     # never built


def test_cli_evidence_writes_a_record_and_follows_the_gate(tmp_path, capsys):
    from keelspec.cli import main

    root = _cli_project(tmp_path)
    main(["-C", str(root), "build"])
    capsys.readouterr()

    assert main(["-C", str(root), "evidence", "-o", "build/ev.json"]) == 0
    record = json.loads((root / "build" / "ev.json").read_text(encoding="utf-8"))
    assert record["result"] == "pass"
    assert record["counts"] == {"terms": 2}

    # break it: evidence still records, but must not report success
    (root / "product" / "terms" / "TERM-ledger.md").unlink()
    assert main(["-C", str(root), "evidence", "-o", "build/ev2.json"]) == 1
    broken = json.loads((root / "build" / "ev2.json").read_text(encoding="utf-8"))
    assert broken["result"] == "fail"


def test_cli_evidence_to_stdout_is_valid_json(tmp_path, capsys):
    from keelspec.cli import main

    root = _cli_project(tmp_path)
    main(["-C", str(root), "build"])
    capsys.readouterr()

    main(["-C", str(root), "evidence"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "keelspec-evidence/1"


def test_cli_orchestrate_dry_run_needs_no_network(tmp_path, capsys):
    from keelspec.cli import main

    root = _cli_project(tmp_path)
    main(["-C", str(root), "build"])
    capsys.readouterr()

    assert main(["-C", str(root), "orchestrate", "TERM-payment", "--dry-run"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "proposed"
    assert [v["lens"] for v in report["verdicts"]] == [
        "correctness", "coverage", "security", "reproduce"]


def test_cli_rejects_a_malformed_resolve_flag(tmp_path, capsys):
    from keelspec.cli import main

    root = _cli_project(tmp_path)
    assert main(["-C", str(root), "orchestrate", "FEAT-x", "--dry-run",
                 "--resolve", "no-equals-sign"]) == 2


def test_cli_build_is_deterministic_across_runs(tmp_path):
    """Byte-stability is what makes PAC-060 and the evidence record trustworthy."""
    from keelspec.cli import main

    root = _cli_project(tmp_path)
    main(["-C", str(root), "build"])
    first = (root / "build" / "out.json").read_bytes()
    main(["-C", str(root), "build"])
    assert (root / "build" / "out.json").read_bytes() == first


# ── the model-facing runners, with a fake client ────────────────────────────
class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _ToolBlock:
    def __init__(self, name, inp, bid="t1"):
        self.type, self.name, self.input, self.id = "tool_use", name, inp, bid


class _Resp:
    def __init__(self, content, stop_reason="end_turn"):
        self.content = content
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def create(self, **kw):
        self.calls.append(kw)
        return self.script.pop(0)


class _FakeClient:
    def __init__(self, script):
        self.messages = _FakeMessages(script)


def test_claude_runner_sends_the_station_model_and_effort(monkeypatch):
    """Per-station model policy is the cost/correctness dial. If every station
    silently inherited one default, the dial would not exist."""
    from keelspec.orchestration import BY_ID, DESIGN_SCHEMA
    from keelspec.runners import ClaudeRunner

    runner = ClaudeRunner(api_key="test")
    runner._client = _FakeClient([_Resp([_Block('{"approach":"a","files":[],'
                                                '"criteria_to_tests":[]}')])])

    data = runner.run(BY_ID["ST-03"], "design it", DESIGN_SCHEMA)
    assert data["approach"] == "a"

    sent = runner._client.messages.calls[0]
    assert sent["model"] == "claude-opus-5"                 # from the roster
    assert sent["output_config"]["effort"] == "high"
    assert sent["thinking"] == {"type": "adaptive"}
    assert sent["output_config"]["format"]["schema"] is DESIGN_SCHEMA


def test_claude_runner_uses_the_cheap_model_where_the_work_is_retrieval():
    from keelspec.orchestration import BY_ID
    from keelspec.runners import ClaudeRunner

    runner = ClaudeRunner(api_key="test")
    runner._client = _FakeClient([_Resp([_Block("a brief")])])
    runner.run(BY_ID["ST-01"], "read the graph")

    sent = runner._client.messages.calls[0]
    assert sent["model"] == "claude-haiku-4-5"
    assert sent["output_config"]["effort"] == "low"


def test_claude_runner_surfaces_a_refusal_rather_than_returning_junk():
    from keelspec.orchestration import BY_ID
    from keelspec.runners import ClaudeRunner

    runner = ClaudeRunner(api_key="test")
    runner._client = _FakeClient([_Resp([], stop_reason="refusal")])
    with pytest.raises(RuntimeError, match="refused"):
        runner.run(BY_ID["ST-03"], "x")


def test_claude_runner_rejects_unparseable_json():
    from keelspec.orchestration import BY_ID, DESIGN_SCHEMA
    from keelspec.runners import ClaudeRunner

    runner = ClaudeRunner(api_key="test")
    runner._client = _FakeClient([_Resp([_Block("not json at all")])])
    with pytest.raises(RuntimeError, match="unparseable"):
        runner.run(BY_ID["ST-03"], "x", DESIGN_SCHEMA)


def test_coding_runner_executes_tools_and_reports_what_it_actually_wrote(tmp_path):
    """The sandbox is the source of truth about files changed, not the model's
    recollection of what it changed."""
    from keelspec.coding import CodingRunner
    from keelspec.orchestration import BY_ID, DEVELOP_SCHEMA

    (tmp_path / "existing.py").write_text("old\n", encoding="utf-8")

    runner = CodingRunner(root=tmp_path, write=True, api_key="test")
    runner._client = _FakeClient([
        _Resp([_ToolBlock("list_files", {"path": "."})], stop_reason="tool_use"),
        _Resp([_ToolBlock("write_file", {"path": "new.py", "content": "print(1)\n"})],
              stop_reason="tool_use"),
        _Resp([_Block("done")]),
        # the final structured call: it under-reports on purpose
        _Resp([_Block('{"files_changed":[],"diff_summary":"added new.py"}')]),
    ])

    data = runner.run(BY_ID["ST-04"], "implement it", DEVELOP_SCHEMA)

    assert (tmp_path / "new.py").read_text(encoding="utf-8") == "print(1)\n"
    assert data["files_changed"] == ["new.py"]        # sandbox wins over the model
    assert data["diff_summary"] == "added new.py"


def test_coding_runner_refuses_to_escape_the_root(tmp_path):
    from keelspec.coding import CodingRunner
    from keelspec.orchestration import BY_ID, DEVELOP_SCHEMA

    root = tmp_path / "project"
    root.mkdir()
    (tmp_path / "outside.txt").write_text("secret\n", encoding="utf-8")

    runner = CodingRunner(root=root, write=True, api_key="test")
    runner._client = _FakeClient([
        _Resp([_ToolBlock("read_file", {"path": "../outside.txt"})], stop_reason="tool_use"),
        _Resp([_Block("blocked")]),
        _Resp([_Block('{"files_changed":[],"diff_summary":"nothing"}')]),
    ])
    runner.run(BY_ID["ST-04"], "read the secret", DEVELOP_SCHEMA)

    # the refusal is fed back to the model as a tool result, not raised
    tool_results = [
        block
        for call in runner._client.messages.calls
        for message in call["messages"]
        if isinstance(message.get("content"), list)
        for block in message["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    assert tool_results, "the tool result was never sent back to the model"
    joined = " ".join(str(b["content"]) for b in tool_results)
    assert "REFUSED" in joined
    assert "secret" not in joined          # the file contents never leaked


def test_coding_runner_stops_at_the_turn_limit_and_says_so(tmp_path):
    """A loop that will not converge must report honestly, not spin."""
    from keelspec.coding import CodingRunner
    from keelspec.orchestration import BY_ID, DEVELOP_SCHEMA

    runner = CodingRunner(root=tmp_path, write=True, api_key="test", max_turns=3)
    runner._client = _FakeClient(
        [_Resp([_ToolBlock("list_files", {"path": "."})], stop_reason="tool_use")] * 3)

    data = runner.run(BY_ID["ST-04"], "spin forever", DEVELOP_SCHEMA)
    assert "without converging" in data["diff_summary"]
    assert data["self_notes"] == "turn limit reached"


def test_coding_runner_delegates_other_stations(tmp_path):
    """Only Develop needs tools; everything else is one structured call."""
    from keelspec.coding import CodingRunner
    from keelspec.orchestration import BY_ID

    class Recorder:
        def __init__(self):
            self.seen = []

        def run(self, station, prompt, schema=None):
            self.seen.append(station.id)
            return {"ok": True}

    rec = Recorder()
    runner = CodingRunner(root=tmp_path, api_key="test", fallback=rec)
    runner.run(BY_ID["ST-03"], "design")
    runner.run(BY_ID["ST-06"], "verify")
    assert rec.seen == ["ST-03", "ST-06"]


# ── integration: the only test that talks to a real model ────────────────────
@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"),
                    reason="set ANTHROPIC_API_KEY to run the integration test")
def test_a_real_station_returns_the_declared_shape():
    """Everything else stubs the model, which means an API change breaks users
    rather than CI. This runs one cheap station against the real endpoint so a
    changed response shape or a renamed parameter is caught here first.

    Deliberately ST-01 (haiku, low effort) and a trivial prompt: enough to exercise
    the request shape and the structured-output contract, cheap enough to run often.
    """
    from keelspec.orchestration import BY_ID, DISAMBIGUATION_SCHEMA
    from keelspec.runners import ClaudeRunner

    runner = ClaudeRunner()
    data = runner.run(
        BY_ID["ST-01"],
        "The acceptance criterion is: 'refund window: 30 days'. Return the "
        "underspecified dimensions a human must resolve. Return at most two.",
        DISAMBIGUATION_SCHEMA,
    )
    assert isinstance(data, dict)
    assert "questions" in data
    assert isinstance(data["questions"], list)
    for q in data["questions"]:
        assert "dimension" in q and "question" in q



def _cli_config(tmp_path):
    """_cli_project builds the tree and returns the root; these need the Config."""
    from keelspec.config import load_config
    root = _cli_project(tmp_path)
    return load_config(str(root / "product.config.yaml"))


# ── PAC-060 names what drifted ───────────────────────────────────────────────
def test_staleness_reports_which_artifacts_differ(tmp_path):
    """'the bundle is stale' tells you to run a command. Naming the artifacts tells
    you whether it is the change you meant to make, which is the reviewer's actual
    question."""
    from keelspec import engine

    config = _cli_config(tmp_path)
    engine.build(config, str(tmp_path))

    bundle_path = tmp_path / "build" / "out.json"
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    data["terms"][0]["definition"] = "tampered"
    bundle_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")

    report = engine.validate(config, str(tmp_path))
    stale = next(d for d in report.errors if d.code == "PAC-060")
    assert "artifact(s) differ" in stale.message
    assert "TERM-" in stale.message                 # it names the id


def test_staleness_reports_additions_and_removals(tmp_path):
    from keelspec import engine

    config = _cli_config(tmp_path)
    engine.build(config, str(tmp_path))

    bundle_path = tmp_path / "build" / "out.json"
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    data["terms"] = [r for r in data["terms"] if r["id"] != "TERM-ledger"]
    bundle_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")

    report = engine.validate(config, str(tmp_path))
    stale = next(d for d in report.errors if d.code == "PAC-060")
    assert "+TERM-ledger" in stale.message          # present in sources, absent in build


# ── validate --json ──────────────────────────────────────────────────────────
def test_validate_json_is_machine_readable(tmp_path, capsys):
    from keelspec.cli import main

    root = _cli_project(tmp_path)
    main(["-C", str(root), "build"])
    capsys.readouterr()

    assert main(["-C", str(root), "validate", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "keelspec-report/1"
    assert payload["result"] == "pass"
    assert payload["counts"] == {"terms": 2}
    assert payload["findings"] == []


def test_validate_json_carries_codes_not_prose(tmp_path, capsys):
    """The point of stable codes is that a consumer never has to parse the message."""
    from keelspec.cli import main

    root = _cli_project(tmp_path)
    main(["-C", str(root), "build"])
    (root / "product" / "terms" / "TERM-ledger.md").unlink()
    capsys.readouterr()

    assert main(["-C", str(root), "validate", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"] == "fail"
    codes = {f["code"] for f in payload["findings"]}
    assert {"PAC-020", "PAC-060"} <= codes
    for finding in payload["findings"]:
        assert set(finding) == {"code", "severity", "where", "message"}


# ── orchestrator run persistence ─────────────────────────────────────────────
def test_a_run_is_kept_even_when_it_is_refuted(tmp_path):
    """A refuted run holds the verdicts and failing cases -- the most useful thing
    it produced. Discarding it because nothing was proposed is backwards."""
    from keelspec.orchestration import Orchestrator, StubRunner, save_report

    refuting = {"security": {"lens": "security", "refuted": True, "severity": "blocker",
                             "reason": "no authz", "failing_case": "unauthenticated POST"}}
    report = Orchestrator(StubRunner(verdicts=refuting), max_repair=1).run("FEAT-refunds")
    assert report.status == "refuted"

    path = save_report(tmp_path, report)
    assert path.parent == tmp_path / ".keelspec" / "runs"

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["status"] == "refuted"
    assert saved["repair_rounds"] == 1
    blocking = [v for v in saved["verdicts"] if v["refuted"]]
    assert blocking[0]["failing_case"] == "unauthenticated POST"


# ── evidence --verify ────────────────────────────────────────────────────────
def test_evidence_verifies_against_an_unchanged_tree(tmp_path):
    from keelspec import engine, evidence

    config = _cli_config(tmp_path)
    engine.build(config, str(tmp_path))
    record = evidence.build_record(config, str(tmp_path))

    assert evidence.verify(record, str(tmp_path)) == []


def test_evidence_verify_detects_a_changed_artifact(tmp_path):
    """This is the whole point of content-addressing: a record nobody can check is
    a claim, not evidence."""
    from keelspec import engine, evidence

    config = _cli_config(tmp_path)
    engine.build(config, str(tmp_path))
    record = evidence.build_record(config, str(tmp_path))

    target = tmp_path / "product" / "terms" / "TERM-payment.md"
    target.write_text(target.read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8")

    problems = evidence.verify(record, str(tmp_path))
    assert any("TERM-payment.md changed" in p for p in problems)


def test_evidence_verify_detects_a_tampered_bundle_and_a_missing_file(tmp_path):
    from keelspec import engine, evidence

    config = _cli_config(tmp_path)
    engine.build(config, str(tmp_path))
    record = evidence.build_record(config, str(tmp_path))

    (tmp_path / "build" / "out.json").write_text("{}", encoding="utf-8")
    (tmp_path / "product" / "terms" / "TERM-ledger.md").unlink()

    problems = evidence.verify(record, str(tmp_path))
    assert any("bundle" in p and "changed" in p for p in problems)
    assert any("TERM-ledger.md is missing" in p for p in problems)


def test_evidence_verify_rejects_an_unknown_schema(tmp_path):
    from keelspec import evidence
    problems = evidence.verify({"schema": "something-else/9"}, str(tmp_path))
    assert problems and "unknown schema" in problems[0]


# ── ST-04b Clean ─────────────────────────────────────────────────────────────
def test_clean_runs_between_develop_and_test():
    """An agent that has just solved a problem leaves the shape of the struggle in
    the code. Nothing downstream asked whether that was the simplest form of it."""
    from keelspec.orchestration import Orchestrator, StubRunner

    report = Orchestrator(StubRunner()).run("FEAT-refunds")
    stations = [s.station for s in report.steps]
    assert stations == ["ST-01", "ST-02", "ST-03", "ST-04", "ST-04b", "ST-05"]
    assert stations.index("ST-04b") > stations.index("ST-04")
    assert stations.index("ST-04b") < stations.index("ST-05")


def test_clean_can_be_skipped():
    from keelspec.orchestration import Orchestrator, StubRunner

    report = Orchestrator(StubRunner(), clean=False).run("FEAT-refunds")
    assert "ST-04b" not in [s.station for s in report.steps]
    assert report.status == "proposed"


def test_a_cleaner_that_admits_changing_behaviour_is_not_trusted():
    """Simplification that alters behaviour is Develop's job done without Develop's
    tests. The claim is recorded; the work is dropped."""
    from keelspec.orchestration import CLEAN_SCHEMA, Orchestrator

    class Overreaching:
        def run(self, station, prompt, schema=None):
            if schema is CLEAN_SCHEMA:
                return {"files_changed": ["a.py"],
                        "simplifications": ["rewrote the retry loop"],
                        "behaviour_preserved": False,
                        "notes": "the old loop retried twice, mine retries once"}
            return {"questions": [], "approach": "a", "files": [],
                    "criteria_to_tests": [], "files_changed": [], "diff_summary": "d",
                    "tests_added": [], "tests_passed": True, "coverage_notes": "c",
                    "lens": "x", "refuted": False, "severity": "none", "reason": "ok"}

    report = Orchestrator(Overreaching()).run("FEAT-refunds")
    assert report.simplifications == []              # not carried forward
    assert any("could not preserve behaviour" in n for n in report.notes)
    assert report.status == "proposed"               # but it does not fail the run


def test_a_well_behaved_cleaner_is_recorded():
    from keelspec.orchestration import CLEAN_SCHEMA, Orchestrator

    class Tidy:
        def run(self, station, prompt, schema=None):
            if schema is CLEAN_SCHEMA:
                return {"files_changed": ["a.py"],
                        "simplifications": ["collapsed duplicate validation",
                                            "named the magic number"],
                        "behaviour_preserved": True, "notes": ""}
            return {"questions": [], "approach": "a", "files": [],
                    "criteria_to_tests": [], "files_changed": [], "diff_summary": "d",
                    "tests_added": [], "tests_passed": True, "coverage_notes": "c",
                    "lens": "x", "refuted": False, "severity": "none", "reason": "ok"}

    report = Orchestrator(Tidy()).run("FEAT-refunds")
    assert report.simplifications == ["collapsed duplicate validation",
                                      "named the magic number"]
    assert json.loads(report.render())["simplifications"] == report.simplifications


def test_inserting_the_cleaner_did_not_renumber_the_roster():
    """Station ids are referenced in decks and diagrams. Renumbering a stable
    reference to make room is the mistake we refuse to make with PAC codes."""
    from keelspec.orchestration import BY_ID, ROSTER

    ids = [s.id for s in ROSTER]
    assert ids == ["ST-01", "ST-02", "ST-03", "ST-04", "ST-04b",
                   "ST-05", "ST-06", "ST-07", "ST-08", "ST-09", "ST-10"]
    assert BY_ID["ST-05"].name == "Test"          # unchanged by the insertion
    assert BY_ID["ST-06"].name == "Verify"
    assert BY_ID["ST-08"].name == "CI gates"


def test_the_cleaner_needs_tools_like_develop(tmp_path):
    from keelspec.coding import CodingRunner
    from keelspec.orchestration import BY_ID

    class Recorder:
        def __init__(self):
            self.seen = []

        def run(self, station, prompt, schema=None):
            self.seen.append(station.id)
            return {"ok": True}

    rec = Recorder()
    runner = CodingRunner(root=tmp_path, api_key="test", fallback=rec)
    runner.run(BY_ID["ST-03"], "design")          # delegated
    assert rec.seen == ["ST-03"]
    assert "ST-04b" not in rec.seen               # Clean is NOT delegated


# ── thinking/effort config: resolution + graceful degrade on models without it ──
# The Haiku `Understand` station (ST-01) rejects BOTH params the roster sends
# uniformly — thinking={"type":"adaptive"} and output_config.effort — each with a
# 400 that names the param, and either one used to sink the whole run at step one.
# These pin the strip-and-retry fix. (Uniquely-named fakes so as not to clobber the
# scripted _FakeClient above.)

class _PickyMessages:
    """A messages stub that 400s when a named param is present (Haiku-like)."""
    def __init__(self, resp, reject=("thinking", "effort"), other_error=None):
        self.resp, self._reject, self._other = resp, set(reject), other_error
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        if self._other is not None and self._other in kw.get("model", ""):
            raise Exception("400 - invalid model")
        if "thinking" in self._reject and "thinking" in kw:
            raise Exception("Error code: 400 - adaptive thinking is not supported on this model")
        if "effort" in self._reject and "effort" in (kw.get("output_config") or {}):
            raise Exception("400 - This model does not support the effort parameter.")
        return self.resp


class _PickyClient:
    def __init__(self, messages):
        self.messages = messages


def test_resolve_thinking_precedence(monkeypatch):
    from keelspec.runners import resolve_thinking
    monkeypatch.delenv("KEELSPEC_THINKING", raising=False)
    assert resolve_thinking() == {"type": "adaptive"}                 # default on
    assert resolve_thinking(None) is None                              # explicit wins over env
    monkeypatch.setenv("KEELSPEC_THINKING", "off")
    assert resolve_thinking() is None
    monkeypatch.setenv("KEELSPEC_THINKING", "enabled:5000")
    assert resolve_thinking() == {"type": "enabled", "budget_tokens": 5000}
    assert resolve_thinking({"type": "adaptive"}) == {"type": "adaptive"}  # explicit still wins


def test_create_message_degrades_when_model_rejects_thinking():
    from keelspec.runners import create_message
    msgs = _PickyMessages("OK", reject=("thinking",))
    resp = create_message(_PickyClient(msgs), {"model": "claude-haiku-4-5", "messages": []},
                          {"type": "adaptive"})
    assert resp == "OK"
    assert len(msgs.calls) == 2                       # once with thinking, once without
    assert "thinking" not in msgs.calls[1]


def test_create_message_degrades_when_model_rejects_effort():
    # `effort` lives inside output_config; stripping it must keep the rest (the schema).
    from keelspec.runners import create_message
    msgs = _PickyMessages("OK", reject=("effort",))
    oc = {"effort": "high", "format": {"type": "json_schema", "schema": {"x": 1}}}
    resp = create_message(_PickyClient(msgs),
                          {"model": "claude-haiku-4-5", "output_config": oc, "messages": []}, None)
    assert resp == "OK"
    assert len(msgs.calls) == 2
    assert "effort" not in msgs.calls[1]["output_config"]
    assert msgs.calls[1]["output_config"]["format"]["schema"] == {"x": 1}   # schema preserved


def test_create_message_strips_both_thinking_and_effort():
    from keelspec.runners import create_message
    msgs = _PickyMessages("OK", reject=("thinking", "effort"))
    oc = {"effort": "high", "format": {"type": "json_schema", "schema": {}}}
    resp = create_message(_PickyClient(msgs),
                          {"model": "claude-haiku-4-5", "output_config": oc, "messages": []},
                          {"type": "adaptive"})
    assert resp == "OK"
    assert len(msgs.calls) == 3                        # thinking, then effort, then clean
    assert "thinking" not in msgs.calls[2] and "effort" not in msgs.calls[2]["output_config"]


def test_create_message_propagates_unfixable_errors():
    from keelspec.runners import create_message
    msgs = _PickyMessages("OK", reject=(), other_error="boom")
    with pytest.raises(Exception, match="invalid model"):
        create_message(_PickyClient(msgs), {"model": "boom", "messages": []}, {"type": "adaptive"})


def test_create_message_omits_thinking_when_none():
    from keelspec.runners import create_message
    msgs = _PickyMessages("OK", reject=("thinking",))   # would raise IF thinking were sent
    resp = create_message(_PickyClient(msgs), {"model": "x", "messages": []}, None)
    assert resp == "OK" and len(msgs.calls) == 1
    assert "thinking" not in msgs.calls[0]


def test_claude_runner_survives_a_haiku_station_end_to_end():
    # ST-01 runs on Haiku, which rejects both params. The station must still return.
    from keelspec.orchestration import BY_ID
    from keelspec.runners import ClaudeRunner

    runner = ClaudeRunner(api_key="test")
    runner._client = _PickyClient(_PickyMessages(_Resp([_Block("hi")]), reject=("thinking", "effort")))
    out = runner.run(BY_ID["ST-01"], "understand")   # haiku station
    assert out == {"text": "hi"}
    calls = runner._client.messages.calls
    assert "thinking" not in calls[-1]                # last (successful) call sent neither
    assert "effort" not in (calls[-1].get("output_config") or {})


# ── OpenAI-compatible runners: the config bridge to a gateway (Muchty/OpenRouter/…) ──
# These let the pipeline be pointed at any /chat/completions endpoint by base_url.
# We patch runners.openai_chat (coding imports it from there at call time) with a
# scripted fake, so no network and no SDK.

def _oai_msg(content=None, tool_calls=None):
    m = {"role": "assistant", "content": content}
    if tool_calls is not None:
        m["tool_calls"] = tool_calls
    return {"choices": [{"message": m}]}, "served-model-x"


def test_openai_runner_parses_structured_json(monkeypatch):
    from keelspec import runners
    from keelspec.orchestration import BY_ID, DESIGN_SCHEMA
    seen = {}
    def fake(base_url, api_key, body, timeout=120.0, extra_headers=None):
        seen.update(base_url=base_url, headers=extra_headers, body=body)
        return _oai_msg('{"approach":"a","files":[],"criteria_to_tests":[]}')
    monkeypatch.setattr(runners, "openai_chat", fake)
    r = runners.OpenAIRunner("https://gw.example/v1", api_key="k",
                             extra_headers={"X-Muchty-Concept": "code.repair"})
    data = r.run(BY_ID["ST-03"], "design it", DESIGN_SCHEMA)
    assert data["approach"] == "a"
    assert seen["base_url"] == "https://gw.example/v1"
    assert seen["headers"]["X-Muchty-Concept"] == "code.repair"   # routing rides on headers
    # Default: NO response_format (gateway-routed Anthropic 400s on it) — JSON is asked
    # for in the prompt instead.
    assert "response_format" not in seen["body"]
    assert "JSON object" in seen["body"]["messages"][-1]["content"]


def test_openai_runner_json_mode_sends_response_format(monkeypatch):
    from keelspec import runners
    from keelspec.orchestration import BY_ID, DESIGN_SCHEMA
    seen = {}
    def fake(base_url, api_key, body, timeout=120.0, extra_headers=None):
        seen["body"] = body
        return _oai_msg('{"approach":"a","files":[],"criteria_to_tests":[]}')
    monkeypatch.setattr(runners, "openai_chat", fake)
    r = runners.OpenAIRunner("https://gw/v1", api_key="k", json_mode=True)   # opt in
    r.run(BY_ID["ST-03"], "design", DESIGN_SCHEMA)
    assert seen["body"]["response_format"] == {"type": "json_object"}


def test_extract_json_object_tolerates_fences_and_prose():
    from keelspec.runners import extract_json_object
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_object('Sure! {"a": 1} done.') == {"a": 1}
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_openai_runner_text_when_no_schema(monkeypatch):
    from keelspec import runners
    from keelspec.orchestration import BY_ID
    monkeypatch.setattr(runners, "openai_chat", lambda *a, **k: _oai_msg("hello"))
    r = runners.OpenAIRunner("https://gw/v1", api_key="k")
    assert r.run(BY_ID["ST-01"], "understand") == {"text": "hello"}


def test_openai_coding_runner_writes_files_via_tool_loop(monkeypatch, tmp_path):
    # Develop routed through an OpenAI endpoint: a tool_call writes a file, the loop
    # ends, and files_changed reflects the sandbox — not the model's say-so.
    from keelspec import runners
    from keelspec.coding import OpenAICodingRunner
    from keelspec.orchestration import BY_ID

    calls = {"n": 0}
    def fake(base_url, api_key, body, timeout=120.0, extra_headers=None):
        calls["n"] += 1
        if calls["n"] == 1:      # first turn → call write_file
            return _oai_msg(None, tool_calls=[{
                "id": "c1", "type": "function",
                "function": {"name": "write_file",
                             "arguments": '{"path": "hello.txt", "content": "hi"}'}}])
        if calls["n"] == 2:      # second turn → no tool calls → converge
            return _oai_msg("done")
        return _oai_msg('{"diff_summary": "wrote hello.txt", "self_notes": ""}')  # final structured
    monkeypatch.setattr(runners, "openai_chat", fake)

    runner = OpenAICodingRunner(root=tmp_path, write=True, base_url="https://gw/v1", api_key="k")
    out = runner.run(BY_ID["ST-04"], "make hello.txt")
    assert (tmp_path / "hello.txt").read_text() == "hi"      # the tool actually wrote it
    assert out["files_changed"] == ["hello.txt"]             # sandbox is source of truth
    assert calls["n"] == 3


def test_openai_coding_runner_delegates_non_develop(monkeypatch, tmp_path):
    # Non-Develop stations go to the OpenAIRunner fallback (one structured call).
    from keelspec import runners
    from keelspec.coding import OpenAICodingRunner
    from keelspec.orchestration import BY_ID, DESIGN_SCHEMA
    monkeypatch.setattr(runners, "openai_chat",
                        lambda *a, **k: _oai_msg('{"approach":"b","files":[],"criteria_to_tests":[]}'))
    runner = OpenAICodingRunner(root=tmp_path, base_url="https://gw/v1", api_key="k")
    assert runner.run(BY_ID["ST-03"], "design", DESIGN_SCHEMA)["approach"] == "b"


def test_openai_runner_guards_non_object_json(monkeypatch):
    # A gateway-routed small model can return a bare JSON string under json_object mode;
    # the runner must raise a CLEAR error, not let a str crash a downstream .get().
    from keelspec import runners
    from keelspec.orchestration import BY_ID, DESIGN_SCHEMA
    monkeypatch.setattr(runners, "openai_chat", lambda *a, **k: _oai_msg('"just a string"'))
    r = runners.OpenAIRunner("https://gw/v1", api_key="k")
    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="non-object JSON"):
        r.run(BY_ID["ST-03"], "design", DESIGN_SCHEMA)


def test_openai_chat_surfaces_http_error_body(monkeypatch):
    # A bare 502 is useless; the gateway's body must appear in the error.
    import io
    import urllib.error

    from keelspec import runners
    def boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {},
                                     io.BytesIO(b'{"error":"upstream anthropic key invalid"}'))
    monkeypatch.setattr("urllib.request.urlopen", boom)
    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="upstream anthropic key invalid"):
        runners.openai_chat("https://gw/v1", "k", {"messages": []})


def test_openai_runner_omits_temperature_by_default(monkeypatch):
    # Claude-5-family models reject `temperature` as deprecated (400); it must be OFF
    # unless explicitly requested.
    from keelspec import runners
    from keelspec.orchestration import BY_ID
    seen = {}
    def fake(base_url, api_key, body, timeout=120.0, extra_headers=None):
        seen["body"] = body
        return _oai_msg("hi")
    monkeypatch.setattr(runners, "openai_chat", fake)
    runners.OpenAIRunner("https://gw/v1", api_key="k").run(BY_ID["ST-01"], "x")
    assert "temperature" not in seen["body"]
    runners.OpenAIRunner("https://gw/v1", api_key="k", temperature=0).run(BY_ID["ST-01"], "x")
    assert seen["body"]["temperature"] == 0                       # opt-in still works


# ── routing by concept, per station ──────────────────────────────────────────
# `extra_headers` is fixed for a whole run, so every station reaches the gateway
# looking like the same kind of request. `concepts` varies the one header that says
# otherwise, which is what lets a router apply a policy per KIND of work.

def _capture_headers(monkeypatch):
    from keelspec import runners
    seen = {}

    def fake(base_url, api_key, body, timeout=120.0, extra_headers=None):
        seen.setdefault("calls", []).append(dict(extra_headers or {}))
        return _oai_msg('{"ok":true}')

    monkeypatch.setattr(runners, "openai_chat", fake)
    return seen


def test_concept_routing_is_off_unless_asked_for(monkeypatch):
    """The default request must stay byte-identical to before this existed."""
    from keelspec import runners
    from keelspec.orchestration import BY_ID
    seen = _capture_headers(monkeypatch)
    runners.OpenAIRunner("https://gw/v1", api_key="k").run(BY_ID["ST-03"], "x", {})
    assert seen["calls"][0] == {}


def test_each_station_carries_its_own_concept(monkeypatch):
    from keelspec import runners
    from keelspec.orchestration import BY_ID
    seen = _capture_headers(monkeypatch)
    r = runners.OpenAIRunner("https://gw/v1", api_key="k",
                             concepts=runners.STATION_CONCEPTS)
    for sid in ("ST-01", "ST-03", "ST-04"):
        r.run(BY_ID[sid], "x", {})
    assert [c["x-fife-concept"] for c in seen["calls"]] == [
        "content.summarize", "spec.disambiguate", "code.repair"]


def test_an_unmapped_station_falls_back_to_the_default_concept(monkeypatch):
    """Adding a station must not silently route it as if it were code repair."""
    from keelspec import runners
    from keelspec.orchestration import BY_ID
    seen = _capture_headers(monkeypatch)
    runners.OpenAIRunner("https://gw/v1", api_key="k",
                         concepts=runners.STATION_CONCEPTS).run(BY_ID["ST-07"], "x", {})
    assert seen["calls"][0]["x-fife-concept"] == runners.DEFAULT_CONCEPT
    assert "ST-07" not in runners.STATION_CONCEPTS


def test_the_catalogue_and_header_belong_to_the_operator(monkeypatch):
    """Concept names are the router operator's, not this library's."""
    from keelspec import runners
    from keelspec.orchestration import BY_ID
    seen = _capture_headers(monkeypatch)
    runners.OpenAIRunner("https://gw/v1", api_key="k",
                         concepts={"ST-03": "planning.deep"},
                         concept_header="x-route-concept",
                         extra_headers={"x-project": "keel"}).run(BY_ID["ST-03"], "x", {})
    assert seen["calls"][0] == {"x-project": "keel", "x-route-concept": "planning.deep"}


def test_develop_gets_its_concept_too(monkeypatch, tmp_path):
    """ST-04 runs its own tool loop rather than delegating, so it has to ask the
    fallback for the same headers every other station would have been given."""
    from keelspec import runners
    from keelspec.coding import OpenAICodingRunner
    from keelspec.orchestration import BY_ID
    seen = _capture_headers(monkeypatch)
    OpenAICodingRunner(tmp_path, base_url="https://gw/v1", api_key="k",
                       concepts=runners.STATION_CONCEPTS).run(BY_ID["ST-04"], "build it")
    assert seen["calls"][0]["x-fife-concept"] == "code.repair"
