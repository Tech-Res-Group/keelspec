"""External builders at ST-04: isolation, diff-based accounting, protected paths.

The agent CLI is faked by a small script that edits files and replies the way
`claude -p --output-format json` does, so these tests run offline and never touch a
real agent or a credential.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import textwrap

import pytest

from keelspec.builders import (BuilderError, ClaudeCodeBuilder, ProtectedPathTouched,
                               _last_json_object, protected_paths)
from keelspec.config import ArtifactType, Config
from keelspec.orchestration import BY_ID, CLEAN_SCHEMA, Orchestrator, StubRunner

FAKE = textwrap.dedent('''
    """A stand-in agent CLI. Each call consumes the next action from the plan file."""
    import json, os, pathlib, sys
    if "--version" in sys.argv:
        print("9.9.9 (fake agent)"); sys.exit(0)
    sys.stdin.read()
    state = pathlib.Path(os.environ["FAKE_PLAN"])
    plan = json.loads(state.read_text())
    action = plan.pop(0) if plan else {"reply": "nothing to do"}
    state.write_text(json.dumps(plan))
    for path, content in (action.get("write") or {}).items():
        target = pathlib.Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    for path in action.get("delete") or []:
        pathlib.Path(path).unlink()
    if action.get("fail"):
        print("boom", file=sys.stderr); sys.exit(3)
    print(json.dumps({"type": "result", "is_error": False, "result": action.get("reply", ""),
                      "total_cost_usd": 0.01, "num_turns": 2}))
''')


def _git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                           *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "product" / "features").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "product" / "features" / "FEAT-x.md").write_text("---\nid: FEAT-x\n---\n")
    (root / "src" / "app.py").write_text("def total(xs):\n    return sum(xs)\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


@pytest.fixture()
def agent(tmp_path, monkeypatch):
    script = tmp_path / "fake_agent.py"
    script.write_text(FAKE)
    plan = tmp_path / "plan.json"

    def configure(*actions):
        plan.write_text(json.dumps(list(actions)))
        monkeypatch.setenv("FAKE_PLAN", str(plan))
        return [sys.executable, str(script)]
    return configure


def _builder(repo, command, **kw):
    cfg = Config(types=[ArtifactType(name="features", dir="features")])
    return ClaudeCodeBuilder(repo, fallback=StubRunner(), command=command,
                             protected=protected_paths(cfg, config_path="product.config.yaml",
                                                       plugin="product_hooks.py"), **kw)


def test_files_changed_come_from_git_not_from_the_agents_claim(repo, agent):
    cmd = agent({"write": {"src/app.py": "def total(xs):\n    return sum(xs) or 0\n",
                           "src/new.py": "X = 1\n"},
                 "reply": 'done {"diff_summary": "I only touched README.md"}'})
    b = _builder(repo, cmd)
    out = b.run(BY_ID["ST-04"], "implement it")
    assert out["files_changed"] == ["src/app.py", "src/new.py"]
    assert "return sum(xs) or 0" in out["diff_summary"]        # the reviewers see the real diff
    assert "a claim, not evidence" in out["self_notes"]
    assert "I only touched README.md" in out["self_notes"]
    # The user's working tree is untouched until the change is applied.
    assert "or 0" not in (repo / "src" / "app.py").read_text()
    b.finish(None)


def test_a_builder_that_edits_the_spec_is_rolled_back_and_fails(repo, agent):
    cmd = agent({"write": {"product/features/FEAT-x.md": "---\nid: FEAT-x\nstatus: shipped\n---\n",
                           "src/app.py": "pass\n"}})
    b = _builder(repo, cmd)
    with pytest.raises(ProtectedPathTouched, match="product/features/FEAT-x.md"):
        b.run(BY_ID["ST-04"], "implement it")
    wt = b.worktree.project_dir
    assert "status" not in (wt / "product" / "features" / "FEAT-x.md").read_text()
    assert (wt / "src" / "app.py").read_text().startswith("def total")   # whole step undone
    b.finish(None)


@pytest.mark.parametrize("path", [".github/workflows/ci.yml", ".keelspec/runs/x.json",
                                  "product.config.yaml", "product_hooks.py",
                                  "build/product.generated.json"])
def test_the_gate_and_its_inputs_are_protected(repo, agent, path):
    b = _builder(repo, agent({"write": {path: "changed\n"}}))
    with pytest.raises(ProtectedPathTouched):
        b.run(BY_ID["ST-04"], "implement it")
    b.finish(None)


def test_the_line_stops_when_develop_is_refused(repo, agent):
    b = _builder(repo, agent({"write": {"product/features/FEAT-x.md": "tampered\n"}}))
    report = Orchestrator(b).run("FEAT-x")
    b.finish(report)
    assert report.status == "error"
    assert any("protected path" in n for n in report.notes)
    assert not report.verdicts                       # nothing was attacked, because nothing was built


def test_a_full_run_records_the_builder_and_saves_the_patch(repo, agent, tmp_path):
    cmd = agent({"write": {"src/app.py": "def total(xs):\n    return sum(xs or [])\n"}},
                {"reply": '{"simplifications": [], "behaviour_preserved": true}'})
    b = _builder(repo, cmd)
    report = Orchestrator(b).run("FEAT-x")
    assert report.status == "proposed"
    patch = tmp_path / "out.patch"
    notes = b.finish(report, patch_path=patch)
    assert "sum(xs or [])" in patch.read_text()
    assert any("not touched" in n for n in notes)
    rec = report.to_dict()["builder"]
    assert rec["name"] == "claude-code" and rec["vendor"] == "anthropic"
    assert rec["version"] == "9.9.9 (fake agent)"
    assert rec["steps"][0]["files"] == ["src/app.py"]
    assert rec["steps"][0]["usage"]["total_cost_usd"] == 0.01
    assert "keelspec-build-" not in _git(repo, "worktree", "list")   # cleaned up


def test_write_applies_the_change_to_the_working_tree(repo, agent):
    b = _builder(repo, agent({"write": {"src/app.py": "def total(xs):\n    return 0\n"}}))
    b.run(BY_ID["ST-04"], "implement it")
    b.finish(None, write=True)
    assert "return 0" in (repo / "src" / "app.py").read_text()


def test_an_untrusted_clean_is_undone_in_the_worktree_too(repo, agent):
    cmd = agent({"write": {"src/app.py": "def total(xs):\n    return sum(xs)  # v1\n"}},
                {"write": {"src/app.py": "total = sum\n"},
                 "reply": '{"simplifications": ["inline"], "behaviour_preserved": false}'})
    b = _builder(repo, cmd)
    b.run(BY_ID["ST-04"], "implement it")
    out = b.run(BY_ID["ST-04b"], "clean it", CLEAN_SCHEMA)
    assert out["behaviour_preserved"] is False
    assert "# v1" in (b.worktree.project_dir / "src" / "app.py").read_text()
    assert b.steps[-1]["reverted"] is True
    b.finish(None)


def test_repair_builds_on_the_previous_step(repo, agent, tmp_path):
    cmd = agent({"write": {"src/a.py": "A = 1\n"}}, {"write": {"src/b.py": "B = 2\n"}})
    b = _builder(repo, cmd)
    assert b.run(BY_ID["ST-04"], "develop")["files_changed"] == ["src/a.py"]
    assert b.run(BY_ID["ST-04"], "repair")["files_changed"] == ["src/b.py"]
    patch = tmp_path / "all.patch"
    b.finish(None, patch_path=patch)
    assert "src/a.py" in patch.read_text() and "src/b.py" in patch.read_text()


def test_other_stations_go_to_the_fallback_unchanged(repo, agent):
    b = _builder(repo, agent())
    assert b.run(BY_ID["ST-03"], "design it") == StubRunner().run(BY_ID["ST-03"], "design it")
    assert b.worktree is None                        # no worktree until something is built


def test_an_agent_failure_is_reported_not_swallowed(repo, agent):
    b = _builder(repo, agent({"fail": True}))
    with pytest.raises(BuilderError, match="exited 3"):
        b.run(BY_ID["ST-04"], "implement it")
    b.finish(None)


def test_outside_a_git_repository_the_builder_refuses(tmp_path, agent):
    plain = tmp_path / "plain"
    plain.mkdir()
    b = ClaudeCodeBuilder(plain, fallback=StubRunner(), command=agent())
    with pytest.raises(BuilderError, match="not inside a git repository"):
        b.run(BY_ID["ST-04"], "implement it")


def test_the_last_json_object_in_a_reply_is_the_claim():
    assert _last_json_object('thinking {"a": 1} then {"b": {"c": 2}}') == {"b": {"c": 2}}
    assert _last_json_object("no json here") == {}


def test_a_failed_develop_stops_the_line_before_test_and_verify():
    class Broken(StubRunner):
        def run(self, station, prompt, schema=None):
            if station.id == "ST-04":
                raise RuntimeError("no build")
            return super().run(station, prompt, schema)

    report = Orchestrator(Broken()).run("FEAT-x")
    assert report.status == "error"
    assert [s.station for s in report.steps][-1] == "ST-04"


def test_the_cli_runs_an_external_builder_end_to_end(repo, agent, monkeypatch, capsys):
    import keelspec.builders as builders
    import keelspec.runners as runners
    from keelspec.cli import main

    (repo / "product.config.yaml").write_text(
        "product_dir: product\noutput: build/product.generated.json\n"
        "types:\n  - name: features\n    dir: features\n    id_prefix: \"FEAT-\"\n")
    assert main(["-C", str(repo), "build"]) == 0
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "bundle")

    cmd = agent({"write": {"src/app.py": "def total(xs):\n    return sum(xs or [])\n"}},
                {"reply": '{"simplifications": [], "behaviour_preserved": true}'})

    class Fake(builders.ClaudeCodeBuilder):
        def __init__(self, root, **kw):
            super().__init__(root, command=cmd, **kw)

    monkeypatch.setitem(builders.BUILDERS, "claude-code", Fake)
    monkeypatch.setattr(runners, "ClaudeRunner", StubRunner)     # offline critics
    capsys.readouterr()

    assert main(["-C", str(repo), "orchestrate", "FEAT-x", "--builder", "claude-code"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["builder"]["name"] == "claude-code"
    assert pathlib.Path(report["builder"]["patch"]).read_text().count("sum(xs or [])") == 1
    assert any("share a model vendor" in n for n in report["notes"])
    assert "or []" not in (repo / "src" / "app.py").read_text()     # no --write, no change
