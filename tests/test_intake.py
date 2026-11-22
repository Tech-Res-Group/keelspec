"""Intake: tickets in, feature files as the source of truth, sync as a proposal."""
from __future__ import annotations

import base64
import json
import subprocess

import pytest
import yaml

from keelspec import intake, validate
from keelspec.engine import build, parse_frontmatter
from keelspec.config import load_config

CONFIG = {
    "product_dir": "product",
    "output": "build/product.generated.json",
    "types": [{"name": "features", "dir": "features", "id_prefix": "FEAT-",
               "required": ["id", "title", "status", "acceptance"],
               "fields": ["title", "status", "outcome", "acceptance"],
               "enums": {"status": ["idea", "building", "shipped"]}}],
}

ISSUE_BODY = """Customers ask for refunds after the window closes.

## Acceptance criteria
- [ ] A refund on day 30 after settlement is accepted.
- [x] A refund on day 31 is rejected with a reason.

## Notes
- this bullet is not a criterion
"""


class Tracker:
    """A fake GitHub + Jira, answering _http_json by URL."""

    def __init__(self):
        self.issues = {}
        self.seen_headers = []

    def issue(self, number=7, title="Refund window", body=ISSUE_BODY, updated="2026-11-01T00:00:00Z"):
        self.issues[f"https://api.github.com/repos/acme/pay/issues/{number}"] = {
            "html_url": f"https://github.com/acme/pay/issues/{number}",
            "title": title, "body": body, "updated_at": updated}

    def __call__(self, url, headers):
        self.seen_headers.append(headers)
        if url in self.issues:
            return self.issues[url]
        if "/rest/api/2/issue/PAY-12" in url:
            return {"fields": {"summary": "Chargeback notice",
                               "description": "h3. Acceptance Criteria\n# Merchant is emailed\n# Ledger is held",
                               "updated": "2026-11-02T00:00:00.000+0000"}}
        raise intake.IntakeError(f"{url}: HTTP 404")


@pytest.fixture()
def tracker(monkeypatch):
    t = Tracker()
    t.issue()
    monkeypatch.setattr(intake, "_http_json", t)
    return t


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "product" / "features").mkdir(parents=True)
    (tmp_path / "product.config.yaml").write_text(yaml.safe_dump(CONFIG))
    return tmp_path


def _cfg(root):
    return load_config(root / "product.config.yaml")


def _import(root, ref="acme/pay#7"):
    plan = intake.plan_import(_cfg(root), root, intake.fetch(ref))
    intake.apply(root, plan)
    return plan


# ── parsing ──────────────────────────────────────────────────────────────────
def test_acceptance_criteria_are_read_from_their_section_only():
    assert intake.acceptance_from(ISSUE_BODY) == [
        "A refund on day 30 after settlement is accepted.",
        "A refund on day 31 is rejected with a reason."]
    assert intake.acceptance_from("h3. Acceptance Criteria\n# One\n# Two\nh3. Other\n# no") == ["One", "Two"]
    assert intake.acceptance_from("**Acceptance criteria**\n1. First\n2) Second") == ["First", "Second"]
    assert intake.acceptance_from("no section here\n- just a list") == []


def test_references_route_to_the_right_tracker(tracker, monkeypatch):
    assert intake.fetch("https://github.com/acme/pay/issues/7").key == "acme/pay#7"
    assert intake.fetch("acme/pay#7").title == "Refund window"
    jira = intake.fetch("https://acme.atlassian.net/browse/PAY-12")
    assert (jira.kind, jira.key, jira.acceptance) == ("jira", "PAY-12", ["Merchant is emailed", "Ledger is held"])
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    with pytest.raises(intake.IntakeError, match="JIRA_BASE_URL"):
        intake.fetch("PAY-12")
    with pytest.raises(intake.IntakeError, match="not a ticket reference"):
        intake.fetch("refunds please")


def test_a_pull_request_is_not_a_ticket(tracker):
    tracker.issues["https://api.github.com/repos/acme/pay/issues/9"] = {"title": "x", "pull_request": {}}
    with pytest.raises(intake.IntakeError, match="pull request"):
        intake.fetch("acme/pay#9")


def test_credentials_come_from_the_environment(tracker, monkeypatch):
    monkeypatch.setenv("JIRA_EMAIL", "bot@example.invalid")
    monkeypatch.setenv("JIRA_API_TOKEN", "tok")
    monkeypatch.delenv("JIRA_PAT", raising=False)
    intake.fetch("https://acme.atlassian.net/browse/PAY-12")
    assert tracker.seen_headers[-1]["Authorization"] == \
        "Basic " + base64.b64encode(b"bot@example.invalid:tok").decode()
    monkeypatch.setenv("JIRA_PAT", "pat")
    intake.fetch("https://acme.atlassian.net/browse/PAY-12")
    assert tracker.seen_headers[-1]["Authorization"] == "Bearer pat"


# ── import ───────────────────────────────────────────────────────────────────
def test_an_imported_ticket_is_a_valid_draft_with_a_sync_record(project, tracker):
    plan = _import(project)
    assert plan.feature == "FEAT-pay-7"
    meta, body = parse_frontmatter(plan.path)
    assert meta["status"] == "idea"
    assert meta["acceptance"][1] == "A refund on day 31 is rejected with a reason."
    assert "Imported from [acme/pay#7](https://github.com/acme/pay/issues/7)" in body
    record = json.loads(intake.state_path(project, "FEAT-pay-7").read_text())
    assert record["revision"] == "2026-11-01T00:00:00Z" and record["key"] == "acme/pay#7"

    cfg = _cfg(project)
    build(cfg, project)
    assert validate(cfg, project).errors == []


def test_a_ticket_without_criteria_still_makes_a_valid_draft(project, tracker):
    tracker.issue(number=8, body="Just an idea, no criteria yet.")
    plan = _import(project, "acme/pay#8")
    meta, _ = parse_frontmatter(plan.path)
    assert "not written in acme/pay#8 yet" in meta["acceptance"][0]
    cfg = _cfg(project)
    build(cfg, project)
    assert validate(cfg, project).errors == []


def test_importing_twice_is_refused(project, tracker):
    _import(project)
    again = intake.plan_import(_cfg(project), project, intake.fetch("acme/pay#7"))
    assert again.action == "error" and "--sync" in again.error


# ── sync ─────────────────────────────────────────────────────────────────────
def _edit(path, **fields):
    meta, body = parse_frontmatter(path)
    meta.update(fields)
    path.write_text("---\n" + yaml.safe_dump(meta, sort_keys=False) + "---\n" + body + "\n")


def test_sync_with_no_ticket_change_is_a_no_op(project, tracker):
    _import(project)
    assert intake.plan_sync(_cfg(project), project, "FEAT-pay-7").action == "unchanged"


def test_a_ticket_change_becomes_a_proposed_update_that_keeps_peoples_fields(project, tracker):
    plan = _import(project)
    _edit(plan.path, status="building", outcome="OUT-refunds")      # people's fields
    tracker.issue(title="Refund window (30 days)", updated="2026-11-05T00:00:00Z")

    sync = intake.plan_sync(_cfg(project), project, "FEAT-pay-7")
    assert sync.action == "update"
    meta = yaml.safe_load(sync.new_text.split("---")[1])
    assert meta["title"] == "Refund window (30 days)"
    assert meta["status"] == "building" and meta["outcome"] == "OUT-refunds"
    assert plan.path.read_text() == sync.old_text                   # planning writes nothing

    intake.apply(project, sync)
    assert intake.plan_sync(_cfg(project), project, "FEAT-pay-7").action == "unchanged"


def test_criteria_tied_to_tests_survive_a_description_only_change(project, tracker):
    plan = _import(project)
    proven = [{"text": "A refund on day 30 after settlement is accepted.",
               "tests": ["tests/test_refunds.py::test_day_30"]},
              "A refund on day 31 is rejected with a reason."]
    _edit(plan.path, acceptance=proven)
    tracker.issue(body="More context first.\n\n" + ISSUE_BODY, updated="2026-11-06T00:00:00Z")

    sync = intake.plan_sync(_cfg(project), project, "FEAT-pay-7")
    assert sync.action == "update"
    assert "More context first." in sync.new_text
    assert yaml.safe_load(sync.new_text.split("---")[1])["acceptance"] == proven


def test_a_field_changed_on_both_sides_stops_for_a_person(project, tracker):
    plan = _import(project)
    _edit(plan.path, title="Refunds: the 30-day rule")
    tracker.issue(title="Refund window v2", updated="2026-11-07T00:00:00Z")
    before = plan.path.read_text()

    sync = intake.plan_sync(_cfg(project), project, "FEAT-pay-7")
    assert sync.action == "conflict" and sync.conflicts == ["title"]
    assert plan.path.read_text() == before


# ── the CLI and the default-branch rule ──────────────────────────────────────
def _git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   cwd=root, check=True, capture_output=True)


def test_cli_sync_applies_only_off_the_default_branch(project, tracker, capsys):
    from keelspec.cli import main

    assert main(["-C", str(project), "intake", "acme/pay#7"]) == 0
    _git(project, "init", "-q", "-b", "main")
    _git(project, "add", "-A")
    _git(project, "commit", "-qm", "import")
    tracker.issue(title="Refund window (30 days)", updated="2026-11-08T00:00:00Z")
    capsys.readouterr()

    assert main(["-C", str(project), "intake", "--sync"]) == 0          # report only
    out = capsys.readouterr().out
    assert "+title: Refund window (30 days)" in out and "changed" in out

    assert main(["-C", str(project), "intake", "--sync", "--apply"]) == 2
    assert "default branch" in capsys.readouterr().err

    _git(project, "switch", "-q", "-c", "intake/sync")
    assert main(["-C", str(project), "intake", "--sync", "--apply"]) == 0
    meta, _ = parse_frontmatter(project / "product" / "features" / "FEAT-pay-7.md")
    assert meta["title"] == "Refund window (30 days)"


def test_cli_needs_exactly_one_of_a_ticket_or_sync(project, tracker):
    from keelspec.cli import main
    assert main(["-C", str(project), "intake"]) == 2
    assert main(["-C", str(project), "intake", "acme/pay#7", "--sync"]) == 2
