"""Bring-your-own builder: run ST-04 Develop through an external coding agent.

KeelSpec's own Develop station (`keelspec.coding`) is a small agent whose safety comes
from its tools: list, read and write beneath one root, with no shell and no network.
Claude Code and Codex are much more capable, and they bring their own tools, so that
guarantee cannot hold for them. Here the guarantee moves from *what the agent can do*
to *what diff the line accepts*:

1. The agent works in a throwaway git worktree, checked out at ``HEAD``, never in
   your working tree.
2. After each step, the worktree is snapshotted as a git tree object. What changed is
   read from git, never from the agent's own account of what it did.
3. A step whose diff touches a **protected path** (the product directory, the
   committed bundle, the config, the plugin, ``.keelspec/`` or CI configuration) is
   rolled back and fails. The thing being judged does not get to edit the spec it is
   judged against, or the gate that judges it.

Credentials are never handled here. Each adapter runs the agent's own CLI, which
authenticates however it is already configured: a personal login on a laptop, or an
API key in CI. The run record names the builder, so an auditor can tell which agent
wrote the change.

Every other station is delegated to ``fallback`` unchanged, so Test, the critics and
Triage judge an external builder exactly as they judge the built-in one.
"""
from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
from typing import Any

from .orchestration import CLEAN_SCHEMA, Station

DEFAULT_TIMEOUT = 30 * 60        # seconds per step; a long build is fine, a hung one is not
DIFF_IN_SUMMARY = 6000           # characters of unified diff handed to the reviewers

# CI configuration an agent must never edit: changing the gate is not building.
CI_PATHS = (".github/", ".gitlab-ci.yml", ".circleci/", "Jenkinsfile",
            "azure-pipelines.yml", "bitbucket-pipelines.yml", ".buildkite/")

INSTRUCTIONS = """\
You are the Develop station on a governed, agent-built lifecycle (KeelSpec).
Work only inside the current directory, which is a scratch git worktree.

Do not edit: {protected}. Those are the product specification, its compiled bundle,
the gate's configuration and CI. A change that touches any of them is rejected and
rolled back automatically.

Do not commit, push, open pull requests or run git commands that rewrite history.
You cannot merge. A separate station tests your work, five critics try to refute it,
a deterministic gate judges it, and a person decides.

When you are done, end your reply with one JSON object and nothing after it:
{example}

The task:

"""

DEVELOP_EXAMPLE = '{"diff_summary": "what you changed and why", "self_notes": "anything a reviewer should know"}'
CLEAN_EXAMPLE = ('{"simplifications": ["..."], "behaviour_preserved": true, '
                 '"notes": "say false if any simplification could change behaviour"}')


class BuilderError(RuntimeError):
    """The external builder could not produce an acceptable change."""


class ProtectedPathTouched(BuilderError):
    """The builder edited something it is judged against. The step was rolled back."""


@dataclasses.dataclass
class StepDiff:
    files: list[str]
    stat: str
    patch: str


def _git(cwd: pathlib.Path, *args: str, check: bool = True, input: str | None = None) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", input=input)
    if check and proc.returncode != 0:
        raise BuilderError(f"git {' '.join(args)} failed: {proc.stderr.strip()[:400]}")
    return proc.stdout


def protected_paths(config: Any = None, *, config_path: str | None = None,
                    plugin: str | None = None) -> list[str]:
    """Repo-relative paths an external builder must not touch, from the project config."""
    paths = [".keelspec/", *CI_PATHS]
    if config is not None:
        paths.append(str(config.product_dir).strip("/").replace("\\", "/") + "/")
        paths.append(str(config.output).replace("\\", "/"))
    for extra in (config_path, plugin):
        if extra:
            paths.append(str(extra).replace("\\", "/"))
    return sorted(set(paths))


def _is_protected(path: str, protected: list[str]) -> bool:
    path = path.replace("\\", "/")
    for p in protected:
        if p.endswith("/"):
            if path.startswith(p) or path == p.rstrip("/"):
                return True
        elif path == p:
            return True
    return False


def _last_json_object(text: str) -> dict:
    """The final JSON object in an agent's reply, or {} if there is none."""
    end = text.rfind("}")
    while end != -1:
        start = text.rfind("{", 0, end)
        while start != -1:
            try:
                value = json.loads(text[start:end + 1])
                if isinstance(value, dict):
                    return value
            except ValueError:
                pass
            start = text.rfind("{", 0, start)
        end = text.rfind("}", 0, end)
    return {}


class Worktree:
    """A detached git worktree at HEAD, with tree-object snapshots per step.

    Snapshots are tree objects (``git write-tree``), not commits: nothing is added to
    any branch, no commit hooks run, and rolling back is ``read-tree --reset -u``.
    """

    def __init__(self, repo: str | pathlib.Path):
        self.repo = pathlib.Path(repo).resolve()
        top = _git(self.repo, "rev-parse", "--show-toplevel", check=False).strip()
        if not top:
            raise BuilderError(f"{self.repo} is not inside a git repository; an external "
                               "builder needs one to isolate and measure its work")
        self.top = pathlib.Path(top).resolve()
        # The project root may be a subdirectory of the repository.
        self.prefix = os.path.relpath(self.repo, self.top).replace("\\", "/")
        self.prefix = "" if self.prefix == "." else self.prefix.rstrip("/") + "/"
        self.base_commit = _git(self.top, "rev-parse", "HEAD").strip()
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="keelspec-build-"))
        _git(self.top, "worktree", "add", "--detach", str(self.dir), self.base_commit)
        self.base_tree = self.tree = self.previous = self._snapshot()

    @property
    def project_dir(self) -> pathlib.Path:
        return self.dir / self.prefix if self.prefix else self.dir

    def _snapshot(self) -> str:
        _git(self.dir, "add", "-A")
        return _git(self.dir, "write-tree").strip()

    def _relative(self, path: str) -> str:
        return path[len(self.prefix):] if self.prefix and path.startswith(self.prefix) else path

    def diff(self, a: str, b: str) -> StepDiff:
        names = _git(self.dir, "diff", "--name-only", "--no-renames", a, b).split()
        stat = _git(self.dir, "diff", "--stat", a, b).strip()
        patch = _git(self.dir, "diff", "--binary", a, b)
        return StepDiff([self._relative(n) for n in names], stat, patch)

    def step(self, protected: list[str]) -> StepDiff:
        """Snapshot after a step. Roll back and raise if a protected path moved."""
        new = self._snapshot()
        change = self.diff(self.tree, new)
        hit = [f for f in change.files if _is_protected(f, protected)]
        if hit:
            self.rollback()
            raise ProtectedPathTouched(
                "the builder edited protected path(s) " + ", ".join(sorted(hit))
                + "; the step was rolled back")
        self.previous, self.tree = self.tree, new
        return change

    def revert_last(self) -> None:
        """Undo the last accepted step, e.g. a Clean that would not vouch for itself."""
        self.tree = self.previous
        self.rollback()

    def rollback(self) -> None:
        """Restore the worktree to the last accepted snapshot."""
        _git(self.dir, "read-tree", "--reset", "-u", self.tree)
        _git(self.dir, "clean", "-fdq")

    def total(self) -> StepDiff:
        return self.diff(self.base_tree, self.tree)

    def remove(self) -> None:
        _git(self.top, "worktree", "remove", "--force", str(self.dir), check=False)
        shutil.rmtree(self.dir, ignore_errors=True)


class ExternalBuilder:
    """Runs ST-04 (Develop and Repair) and ST-04b (Clean) through an external agent.

    Subclasses say how to invoke the agent; this class owns isolation, accounting and
    the protected-path rule. Use it as the orchestrator's runner.
    """

    name = "external"
    vendor = "unknown"

    def __init__(self, root: str | pathlib.Path = ".", *, fallback: Any,
                 protected: list[str] | None = None,
                 command: list[str] | None = None,
                 timeout: float = DEFAULT_TIMEOUT):
        self.root = pathlib.Path(root).resolve()
        self.fallback = fallback
        self.protected = list(protected if protected is not None else protected_paths())
        self.command = command
        self.timeout = timeout
        self.worktree: Worktree | None = None
        self.version = ""
        self.steps: list[dict] = []

    # ── what a subclass provides ─────────────────────────────────────────────
    def executable(self) -> list[str]:
        raise NotImplementedError

    def invoke(self, prompt: str, cwd: pathlib.Path) -> tuple[str, dict]:
        """Run the agent once. Return its final text and any usage it reports."""
        raise NotImplementedError

    def probe_version(self) -> str:
        try:
            proc = subprocess.run([*self.executable(), "--version"], capture_output=True,
                                  text=True, timeout=30, encoding="utf-8", errors="replace")
            return proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""
        except (OSError, subprocess.SubprocessError, IndexError):
            return ""

    # ── shared machinery ─────────────────────────────────────────────────────
    def _run_process(self, args: list[str], prompt: str, cwd: pathlib.Path) -> str:
        try:
            proc = subprocess.run(args, cwd=cwd, input=prompt, capture_output=True,
                                  text=True, timeout=self.timeout,
                                  encoding="utf-8", errors="replace")
        except FileNotFoundError as exc:
            raise BuilderError(f"{self.name}: cannot run {args[0]!r} ({exc})") from exc
        except subprocess.TimeoutExpired as exc:
            raise BuilderError(f"{self.name}: no result within {int(self.timeout)}s") from exc
        if proc.returncode != 0:
            raise BuilderError(f"{self.name} exited {proc.returncode}: "
                               f"{(proc.stderr or proc.stdout).strip()[:600]}")
        return proc.stdout

    def _ensure_worktree(self) -> Worktree:
        if self.worktree is None:
            self.worktree = Worktree(self.root)
            self.version = self.probe_version()
        return self.worktree

    def describe(self) -> dict:
        """Who built the change, for the run record."""
        wt = self.worktree
        return {
            "name": self.name,
            "vendor": self.vendor,
            "version": self.version,
            "base_commit": wt.base_commit if wt else "",
            "tree": wt.tree if wt else "",
            "protected": self.protected,
            "steps": self.steps,
        }

    def run(self, station: Station, prompt: str, schema: dict | None = None) -> dict:
        if station.id not in ("ST-04", "ST-04b"):
            return self.fallback.run(station, prompt, schema)

        wt = self._ensure_worktree()
        cleaning = station.id == "ST-04b" or schema is CLEAN_SCHEMA
        framed = INSTRUCTIONS.format(
            protected=", ".join(self.protected),
            example=CLEAN_EXAMPLE if cleaning else DEVELOP_EXAMPLE) + prompt

        text, usage = self.invoke(framed, wt.project_dir)
        claim = _last_json_object(text)
        change = wt.step(self.protected)          # raises, after rolling back, on a violation
        self.steps.append({"station": station.id, "files": change.files, "usage": usage})

        if cleaning:
            preserved = claim.get("behaviour_preserved") is True
            if not preserved and change.files:
                # The orchestrator will not carry an untrusted Clean forward, so the
                # worktree must not either.
                wt.revert_last()
                self.steps[-1]["reverted"] = True
            return {
                "files_changed": change.files,
                "simplifications": [str(s) for s in claim.get("simplifications") or []],
                "behaviour_preserved": preserved,
                "notes": str(claim.get("notes") or ""),
            }

        summary = change.stat or "(no files changed)"
        if change.patch:
            summary += "\n\n" + change.patch[:DIFF_IN_SUMMARY]
            if len(change.patch) > DIFF_IN_SUMMARY:
                summary += f"\n... ({len(change.patch) - DIFF_IN_SUMMARY} more characters of diff)"
        notes = f"built by {self.name}"
        if claim.get("diff_summary"):
            notes += f"; the builder's own summary (a claim, not evidence): {claim['diff_summary']}"
        if claim.get("self_notes"):
            notes += f"; builder notes: {claim['self_notes']}"
        return {"files_changed": change.files, "diff_summary": summary, "self_notes": notes}

    def finish(self, report: Any, *, write: bool = False,
               patch_path: pathlib.Path | None = None) -> list[str]:
        """Record the builder on the report, save the patch, and optionally apply it.

        Returns human-readable notes about what happened to the change.
        """
        notes: list[str] = []
        wt = self.worktree
        if report is not None:
            report.builder = self.describe()
        if wt is None:
            return notes
        try:
            total = wt.total()
            if not total.patch:
                notes.append(f"{self.name} produced no change")
                return notes
            if patch_path is not None:
                patch_path.parent.mkdir(parents=True, exist_ok=True)
                patch_path.write_text(total.patch, encoding="utf-8", newline="\n")
                notes.append(f"the change is saved as {patch_path}")
                if report is not None:
                    report.builder["patch"] = str(patch_path)
            if write:
                _git(wt.top, "apply", "--whitespace=nowarn", "-", input=total.patch)
                notes.append(f"applied to your working tree: {', '.join(total.files)}")
            else:
                notes.append("your working tree was not touched (pass --write to apply it)")
        finally:
            wt.remove()
            self.worktree = None
        return notes


class ClaudeCodeBuilder(ExternalBuilder):
    """Claude Code in headless mode (``claude -p``).

    File edits are accepted inside the worktree; the shell and web tools are disabled
    by default. That is defence in depth only -- the diff check is the guarantee.
    """

    name = "claude-code"
    vendor = "anthropic"
    DISALLOWED = ("Bash", "WebFetch", "WebSearch")

    def __init__(self, root: str | pathlib.Path = ".", *, allow_shell: bool = False,
                 model: str | None = None, **kwargs: Any):
        super().__init__(root, **kwargs)
        self.allow_shell = allow_shell
        self.model = model

    def executable(self) -> list[str]:
        if self.command:
            return list(self.command)
        exe = os.getenv("KEELSPEC_CLAUDE_BIN") or shutil.which("claude")
        if not exe:
            raise BuilderError("claude-code: the `claude` CLI is not on PATH "
                               "(install Claude Code, or set KEELSPEC_CLAUDE_BIN)")
        return [exe]

    def invoke(self, prompt: str, cwd: pathlib.Path) -> tuple[str, dict]:
        args = [*self.executable(), "-p", "--output-format", "json",
                "--permission-mode", "acceptEdits"]
        if not self.allow_shell:
            args += ["--disallowedTools", *self.DISALLOWED]
        if self.model:
            args += ["--model", self.model]
        out = self._run_process(args, prompt, cwd)
        try:
            data = json.loads(out)
        except ValueError:
            return out, {}
        if data.get("is_error"):
            raise BuilderError(f"claude-code reported an error: {str(data.get('result'))[:600]}")
        # Keep what cost metrics need; the CLI's full usage block is per-iteration
        # detail that would bloat every run record.
        usage = {k: data[k] for k in ("total_cost_usd", "num_turns", "duration_ms") if k in data}
        tokens = data.get("usage") or {}
        usage.update({k: tokens[k] for k in ("input_tokens", "output_tokens",
                                             "cache_creation_input_tokens",
                                             "cache_read_input_tokens") if k in tokens})
        return str(data.get("result") or ""), usage


class CodexBuilder(ExternalBuilder):
    """OpenAI Codex CLI in non-interactive mode (``codex exec``), sandboxed to the
    worktree by Codex's own ``workspace-write`` mode."""

    name = "codex"
    vendor = "openai"

    def __init__(self, root: str | pathlib.Path = ".", *, model: str | None = None,
                 **kwargs: Any):
        super().__init__(root, **kwargs)
        self.model = model

    def executable(self) -> list[str]:
        if self.command:
            return list(self.command)
        exe = os.getenv("KEELSPEC_CODEX_BIN") or shutil.which("codex")
        if not exe:
            raise BuilderError("codex: the `codex` CLI is not on PATH "
                               "(install Codex CLI, or set KEELSPEC_CODEX_BIN)")
        return [exe]

    def invoke(self, prompt: str, cwd: pathlib.Path) -> tuple[str, dict]:
        with tempfile.TemporaryDirectory(prefix="keelspec-codex-") as tmp:
            last = pathlib.Path(tmp) / "last-message.txt"
            args = [*self.executable(), "exec", "--sandbox", "workspace-write",
                    "--cd", str(cwd), "--output-last-message", str(last)]
            if self.model:
                args += ["--model", self.model]
            out = self._run_process([*args, "-"], prompt, cwd)
            text = last.read_text(encoding="utf-8", errors="replace") if last.exists() else out
        return text, {}


BUILDERS = {"claude-code": ClaudeCodeBuilder, "codex": CodexBuilder}
