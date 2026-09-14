"""Evidence records — what was checked, when, on what, and with what result.

The audit claim KeelSpec makes is that your product model is *provable* rather than
asserted. Git plus determinism already make that true; this module makes it
portable, so the answer to "show me your controls and the evidence they ran" is a
file rather than a walkthrough of somebody's terminal.

An evidence record is content-addressed, not signed. Every artifact, the config and
the bundle carry a SHA-256, so anyone can verify the record by recomputing the
digests — no key to distribute, no trust in the issuer required. That is a stronger
property than a signature for this purpose: a signature proves who made a claim, a
digest proves the claim is true.

Historical evidence needs no special support. Check out the commit and run it
again; byte-stable bundles mean you get the same digests. That *is* the audit
story, and inventing a `--since` that walks history would only hide it.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
from datetime import datetime, timezone

from .config import Config
from .diagnostics import CODES
from .engine import load, render_bundle, validate

SCHEMA = "keelspec-evidence/1"


def _sha256(path: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _git(root: pathlib.Path, *args: str) -> str | None:
    """A git fact, or None when this is not a repository / git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _repository(root: pathlib.Path) -> dict:
    commit = _git(root, "rev-parse", "HEAD")
    if commit is None:
        return {"tracked": False}
    status = _git(root, "status", "--porcelain")
    return {
        "tracked": True,
        "commit": commit,
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        # A dirty tree means the record describes files that are not committed
        # anywhere. Say so loudly rather than let it be inferred.
        "clean": status == "",
        "uncommitted_files": len([line for line in (status or "").splitlines() if line.strip()]),
    }


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("keelspec")
    except Exception:
        return "unknown"


def build_record(config: Config, root: str | pathlib.Path = ".", registry=None) -> dict:
    """Validate, digest everything, and return the evidence record."""
    root_path = pathlib.Path(root).resolve()
    report = validate(config, root, registry)
    bundle = load(config, root)

    artifacts: dict[str, list[dict]] = {}
    for name, records in bundle.items():
        entries = []
        for rec in records:
            rel = rec.get("_file", "")
            entries.append({
                "id": rec.get("id"),
                "file": rel,
                "sha256": _sha256(root_path / rel),
            })
        artifacts[name] = sorted(entries, key=lambda e: (e["file"] or "", e["id"] or ""))

    output = root_path / config.output
    expected = render_bundle(config, root, registry)
    committed = output.read_text(encoding="utf-8") if output.exists() else None

    findings = [
        {
            "code": d.code,
            "severity": d.severity,
            "where": d.where,
            "message": d.message,
        }
        for d in sorted(report.diagnostics, key=lambda d: (d.severity, d.code, d.where))
    ]

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool": {"name": "keelspec", "version": _version()},
        "repository": _repository(root_path),
        "config": {
            "product_dir": str(config.product_dir),
            "output": str(config.output),
            "types": [
                {
                    "name": t.name,
                    "dir": t.dir,
                    "id_prefix": t.id_prefix,
                    "required": list(t.required),
                    "references": [{"field": r.field, "to": r.to} for r in t.references],
                }
                for t in config.types
            ],
        },
        "bundle": {
            "path": str(config.output),
            "sha256": _sha256(output),
            # The whole point of PAC-060, restated as a verifiable field.
            "matches_sources": committed == expected,
        },
        "artifacts": artifacts,
        "counts": {name: len(records) for name, records in bundle.items()},
        "checks": {
            "codes_registered": sorted(CODES),
            "errors": len(report.errors),
            "warnings": len(report.warnings),
        },
        "findings": findings,
        "result": "pass" if report.ok else "fail",
    }


def render(record: dict) -> str:
    """Stable serialisation, so two runs on one commit produce identical bytes
    apart from generated_at."""
    return json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def verify(record: dict, root: str | pathlib.Path = ".") -> list[str]:
    """Recompute every digest in a record and report what no longer matches.

    Content-addressing is only worth anything if somebody can check it. Producing
    a record nobody can verify is a claim, not evidence -- so this is the other
    half of `build_record`, and it needs no key, no trust in the issuer, and no
    network.

    Returns an empty list when the record still describes the tree on disk.
    """
    root_path = pathlib.Path(root).resolve()
    problems: list[str] = []

    if record.get("schema") != SCHEMA:
        problems.append(f"unknown schema: {record.get('schema')!r} (expected {SCHEMA})")
        return problems

    for collection, entries in (record.get("artifacts") or {}).items():
        for entry in entries:
            rel = entry.get("file") or ""
            expected = entry.get("sha256")
            actual = _sha256(root_path / rel)
            if actual is None:
                problems.append(f"{collection}: {rel} is missing")
            elif expected != actual:
                problems.append(f"{collection}: {rel} changed since the record was made")

    bundle = record.get("bundle") or {}
    if bundle.get("path"):
        actual = _sha256(root_path / bundle["path"])
        if actual is None:
            problems.append(f"bundle {bundle['path']} is missing")
        elif actual != bundle.get("sha256"):
            problems.append(f"bundle {bundle['path']} changed since the record was made")

    repo = record.get("repository") or {}
    if repo.get("tracked") and repo.get("commit"):
        head = _git(root_path, "rev-parse", "HEAD")
        if head and head != repo["commit"]:
            problems.append(
                f"the record was made at {repo['commit'][:12]}, the tree is at {head[:12]}"
            )

    return problems
