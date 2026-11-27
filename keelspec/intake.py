"""Intake: turn tickets into feature files, and keep them in step.

The feature file is the source of truth. A ticket is an input channel: every change
to it must reach the file, but only as a proposed change that a person merges. So:

- ``keelspec intake <ticket>`` writes a draft feature (status from the config, the
  ticket's acceptance criteria as bare strings) and records what it imported.
- ``keelspec intake --sync`` finds every imported ticket whose revision has moved and
  shows the change it would make to the file. ``--apply`` writes it, and refuses on
  the default branch: the change is meant to be committed on a branch and merged
  through the gate like any other.
- If a person has also edited a field the ticket owns since the last sync, sync
  shows both sides and stops. It never picks a winner.

The ticket owns three things: the title, the acceptance criteria and the description
block in the body. Everything else in the file (status, outcome, NFRs, owner, prose
outside the block) belongs to people and is never touched by sync.

What was last synced lives in ``.keelspec/intake/<feature>.json``. Commit it.

Sources: GitHub Issues and Jira, over their REST APIs with the standard library.
Credentials come from the environment only: ``GH_TOKEN`` or ``GITHUB_TOKEN``
(optional for public repositories), and ``JIRA_BASE_URL`` with either
``JIRA_EMAIL`` + ``JIRA_API_TOKEN`` (Cloud) or ``JIRA_PAT`` (Server/Data Center).
No ticket content is sent to any model.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import pathlib
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import yaml

from .config import Config
from .engine import parse_frontmatter

BLOCK_START = "<!-- keelspec:intake {key} -->"
BLOCK_END = "<!-- /keelspec:intake -->"
NO_CRITERIA = "Acceptance criteria are not written in {key} yet; settle them at the human gate."


class IntakeError(RuntimeError):
    """A ticket could not be fetched, parsed or written."""


@dataclasses.dataclass
class Ticket:
    kind: str            # "github" | "jira"
    key: str             # "owner/repo#42" | "PAY-123"
    url: str
    title: str
    description: str
    revision: str        # the tracker's last-updated timestamp

    @property
    def acceptance(self) -> list[str]:
        return acceptance_from(self.description) or [NO_CRITERIA.format(key=self.key)]


# ── fetching ─────────────────────────────────────────────────────────────────
def _http_json(url: str, headers: dict[str, str]) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise IntakeError(f"{url}: HTTP {exc.code}") from exc
    except (urllib.error.URLError, ValueError) as exc:
        raise IntakeError(f"{url}: {exc}") from exc


GITHUB_URL = re.compile(r"https?://github\.com/([^/]+)/([^/]+)/issues/(\d+)")
GITHUB_SHORT = re.compile(r"^([\w.-]+)/([\w.-]+)#(\d+)$")
JIRA_URL = re.compile(r"(https?://[^/]+)/browse/([A-Z][A-Z0-9_]+-\d+)")
JIRA_KEY = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")


def fetch(ref: str) -> Ticket:
    """Fetch a ticket by URL, ``owner/repo#N`` or a Jira key."""
    ref = ref.strip()
    m = GITHUB_URL.match(ref) or GITHUB_SHORT.match(ref)
    if m:
        return _fetch_github(*m.groups())
    m = JIRA_URL.match(ref)
    if m:
        return _fetch_jira(m.group(2), m.group(1))
    if JIRA_KEY.match(ref):
        base = os.getenv("JIRA_BASE_URL")
        if not base:
            raise IntakeError(f"{ref}: set JIRA_BASE_URL to fetch a bare Jira key")
        return _fetch_jira(ref, base)
    raise IntakeError(f"not a ticket reference I can fetch: {ref!r} "
                      "(a GitHub issue URL, owner/repo#N, a Jira URL or a Jira key)")


def _fetch_github(owner: str, repo: str, number: str) -> Ticket:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = _http_json(f"https://api.github.com/repos/{owner}/{repo}/issues/{number}", headers)
    if "pull_request" in data:
        raise IntakeError(f"{owner}/{repo}#{number} is a pull request, not an issue")
    return Ticket("github", f"{owner}/{repo}#{number}",
                  data.get("html_url") or f"https://github.com/{owner}/{repo}/issues/{number}",
                  str(data.get("title") or "").strip(), str(data.get("body") or ""),
                  str(data.get("updated_at") or ""))


def _fetch_jira(key: str, base: str) -> Ticket:
    base = base.rstrip("/")
    headers: dict[str, str] = {}
    if os.getenv("JIRA_PAT"):
        headers["Authorization"] = f"Bearer {os.environ['JIRA_PAT']}"
    elif os.getenv("JIRA_EMAIL") and os.getenv("JIRA_API_TOKEN"):
        pair = f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(pair).decode()
    # API v2 returns the description as text (wiki markup), not Atlassian Document
    # Format, which keeps parsing deterministic and dependency-free.
    query = urllib.parse.urlencode({"fields": "summary,description,updated"})
    data = _http_json(f"{base}/rest/api/2/issue/{key}?{query}", headers)
    fields = data.get("fields") or {}
    return Ticket("jira", key, f"{base}/browse/{key}",
                  str(fields.get("summary") or "").strip(),
                  str(fields.get("description") or ""), str(fields.get("updated") or ""))


# ── parsing ──────────────────────────────────────────────────────────────────
HEADING = re.compile(
    r"^\s*(?:#{1,6}\s*|h[1-6]\.\s*|\*{1,2})?acceptance[ _-]criteria\b.*$", re.IGNORECASE)
NEXT_HEADING = re.compile(r"^\s*(?:#{1,6}\s+|h[1-6]\.\s+)\S")
BULLET = re.compile(r"^\s*(?:[-*+]|#|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.+?)\s*$")


def acceptance_from(description: str) -> list[str]:
    """The bullets under an "Acceptance criteria" heading, in order.

    Markdown (``## Acceptance criteria``, ``**Acceptance criteria**``) and Jira wiki
    markup (``h3. Acceptance Criteria``, ``# item``) are both understood. Anything
    that is not a bullet in that section is ignored rather than guessed at.
    """
    lines = description.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    inside = False
    for line in lines:
        if HEADING.match(line):
            inside, out = True, []
            continue
        if inside:
            if NEXT_HEADING.match(line) and not BULLET.match(line):
                break
            m = BULLET.match(line)
            if m:
                out.append(m.group(1).strip())
    return out


def feature_id(ticket: Ticket, prefix: str) -> str:
    """A stable id from the ticket key, so renaming a ticket never renames the file."""
    if ticket.kind == "github":
        _owner, rest = ticket.key.split("/", 1)
        repo, number = rest.split("#")
        slug = f"{repo}-{number}"
    else:
        slug = ticket.key
    return prefix + re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")


# ── the file and its sync record ─────────────────────────────────────────────
def state_path(root: str | pathlib.Path, feature: str) -> pathlib.Path:
    return pathlib.Path(root) / ".keelspec" / "intake" / f"{feature}.json"


def _block(ticket: Ticket) -> str:
    text = ticket.description.strip() or "(no description in the ticket)"
    return (f"{BLOCK_START.format(key=ticket.key)}\n"
            f"Imported from [{ticket.key}]({ticket.url}).\n\n{text}\n{BLOCK_END}")


def _replace_block(body: str, key: str, block: str) -> str:
    start = BLOCK_START.format(key=key)
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(BLOCK_END), re.DOTALL)
    if pattern.search(body):
        return pattern.sub(lambda _m: block, body, count=1)
    return block + ("\n\n" + body.lstrip() if body.strip() else "\n")


def _read_block(body: str, key: str) -> str:
    start = BLOCK_START.format(key=key)
    m = re.search(re.escape(start) + r"(.*?)" + re.escape(BLOCK_END), body, re.DOTALL)
    return m.group(0) if m else ""


def _render(meta: dict, body: str) -> str:
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000)
    return f"---\n{front}---\n{body.strip()}\n"


def _owned(ticket: Ticket) -> dict:
    return {"title": ticket.title, "acceptance": ticket.acceptance, "block": _block(ticket)}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


@dataclasses.dataclass
class Plan:
    """What intake would do to one feature file."""
    feature: str
    path: pathlib.Path
    ticket: Ticket | None
    action: str                    # create | update | unchanged | conflict | error
    new_text: str = ""
    old_text: str = ""
    conflicts: list[str] = dataclasses.field(default_factory=list)
    error: str = ""


def _type_for(config: Config):
    name = config.intake.type if config.intake else "features"
    t = config.type_by_name(name)
    if t is None:
        raise IntakeError(f"intake writes to type {name!r}, which product.config.yaml "
                          "does not declare (set intake.type)")
    return t


def _status(config: Config, t) -> str | None:
    if config.intake and config.intake.status:
        return config.intake.status
    allowed = t.enums.get("status")
    if allowed:
        return "idea" if "idea" in allowed else allowed[0]
    return "idea" if "status" in t.fields or "status" in t.required else None


def plan_import(config: Config, root: str | pathlib.Path, ticket: Ticket,
                feature: str | None = None) -> Plan:
    t = _type_for(config)
    fid = feature or feature_id(ticket, t.id_prefix or "")
    path = pathlib.Path(root) / config.product_dir / t.dir / f"{fid}.md"
    if path.exists() or state_path(root, fid).exists():
        return Plan(fid, path, ticket, "error",
                    error=f"{fid} already exists; use --sync to bring it up to date")
    meta: dict[str, Any] = {"id": fid, "title": ticket.title}
    status = _status(config, t)
    if status:
        meta["status"] = status
    if config.intake and config.intake.link_field:
        meta[config.intake.link_field] = ticket.url
    meta["acceptance"] = ticket.acceptance
    return Plan(fid, path, ticket, "create", new_text=_render(meta, _block(ticket)))


def plan_sync(config: Config, root: str | pathlib.Path, feature: str,
              fetcher=None) -> Plan:
    fetcher = fetcher or fetch
    t = _type_for(config)
    state = json.loads(state_path(root, feature).read_text(encoding="utf-8"))
    path = pathlib.Path(root) / config.product_dir / t.dir / f"{feature}.md"
    try:
        ticket = fetcher(state["url"])
    except IntakeError as exc:
        return Plan(feature, path, None, "error", error=str(exc))
    if not path.exists():
        return Plan(feature, path, ticket, "error",
                    error=f"{path} was deleted; the sync record is left for a person")
    if ticket.revision == state.get("revision"):
        return Plan(feature, path, ticket, "unchanged")

    meta, body = parse_frontmatter(path)
    old_text = path.read_text(encoding="utf-8")
    current = {"title": meta.get("title"), "acceptance": meta.get("acceptance"),
               "block": _read_block(body, ticket.key)}
    synced = state.get("synced") or {}
    incoming = _owned(ticket)

    # Conflict only where a person changed a ticket-owned field since the last sync
    # AND the ticket changed it too. Status, outcome and the rest are never compared.
    conflicts = [k for k in ("title", "acceptance", "block")
                 if _digest(current[k]) != synced.get(k)
                 and _digest(incoming[k]) != synced.get(k)
                 and _digest(current[k]) != _digest(incoming[k])]
    if conflicts:
        return Plan(feature, path, ticket, "conflict", old_text=old_text, conflicts=conflicts)

    # Replace only what the ticket changed. A criterion a person has since tied to a
    # test must survive a ticket edit that only touched the description.
    moved = {k for k in ("title", "acceptance", "block")
             if _digest(incoming[k]) != synced.get(k)}
    if "title" in moved:
        meta["title"] = incoming["title"]
    if "acceptance" in moved:
        meta["acceptance"] = incoming["acceptance"]
    if "block" in moved:
        body = _replace_block(body, ticket.key, incoming["block"])
    new_text = _render(meta, body)
    if new_text == old_text:
        return Plan(feature, path, ticket, "unchanged")
    return Plan(feature, path, ticket, "update", new_text=new_text, old_text=old_text)


def tracked(root: str | pathlib.Path) -> list[str]:
    """Every feature intake has imported, from its sync records."""
    return sorted(p.stem for p in (pathlib.Path(root) / ".keelspec" / "intake").glob("*.json"))


def apply(root: str | pathlib.Path, plan: Plan) -> None:
    """Write the file and record what was synced."""
    assert plan.ticket is not None and plan.action in ("create", "update", "unchanged")
    if plan.action in ("create", "update"):
        plan.path.parent.mkdir(parents=True, exist_ok=True)
        plan.path.write_text(plan.new_text, encoding="utf-8", newline="\n")
    owned = _owned(plan.ticket)
    record = {"source": plan.ticket.kind, "key": plan.ticket.key, "url": plan.ticket.url,
              "revision": plan.ticket.revision,
              "synced": {k: _digest(v) for k, v in owned.items()}}
    target = state_path(root, plan.feature)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8", newline="\n")


# ── the default-branch rule ──────────────────────────────────────────────────
def on_default_branch(root: str | pathlib.Path) -> bool:
    """True when HEAD is the repository's default branch (or main/master)."""
    def git(*args: str) -> str:
        proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
        return proc.stdout.strip() if proc.returncode == 0 else ""
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if not branch:
        return False                       # not a git repository: nothing to protect
    default = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD").split("/", 1)[-1]
    return branch == default if default else branch in ("main", "master")
