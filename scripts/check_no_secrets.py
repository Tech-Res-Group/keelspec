"""Fail the build if anything secret-shaped is about to be published.

A PyPI version can be yanked but never replaced, so a leaked credential in a
release is permanent and public. That is exactly the kind of thing a gate should
catch rather than a person remembering — the same argument the product makes about
product intent, applied to our own supply chain.

Two checks:

1. **The package tree** (`keelspec/`) contains no credential-shaped strings.
2. **The built sdist and wheel** contain no credential-shaped strings, and the
   sdist ships none of the operational directories, so a future untracked `.env`
   under `site/` or `infra/` cannot ride along.

    python scripts/check_no_secrets.py            # source tree only
    python scripts/check_no_secrets.py --dist     # also scan dist/*
"""
from __future__ import annotations

import pathlib
import re
import sys
import tarfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bcrypt hash", re.compile(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}")),
    ("Postmark-style token", re.compile(
        r"(?i)postmark[^\n]{0,40}\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
        r"[0-9a-f]{4}-[0-9a-f]{12}\b")),
    ("assigned credential", re.compile(
        r"(?i)\b(api[_-]?key|auth[_-]?token|access[_-]?token|secret|password|passwd)"
        r"\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']")),
]

# Placeholders and documentation are not leaks.
ALLOW = re.compile(
    r"(?i)(PASTE|YOUR[_-]?|EXAMPLE|CHANGE[_-]?ME|xxx+|\.\.\.|<[^>]+>|"
    r"sk-ant-api03-\.\.\.|test-key|dummy|placeholder|unset)")

# The sdist must not carry operational directories.
FORBIDDEN_IN_SDIST = ("/site/", "/infra/", "/.keelspec/")


def scan_text(label: str, text: str) -> list[str]:
    out = []
    for name, rx in PATTERNS:
        for m in rx.finditer(text):
            snippet = m.group(0)
            line = text[max(0, m.start() - 60):m.end() + 20]
            if ALLOW.search(line):
                continue
            out.append(f"{label}: [{name}] {snippet[:60]}")
    return out


def scan_tree() -> list[str]:
    findings = []
    for path in sorted((ROOT / "keelspec").rglob("*.py")):
        findings += scan_text(str(path.relative_to(ROOT)),
                              path.read_text(encoding="utf-8", errors="replace"))
    return findings


def scan_dist() -> list[str]:
    findings = []
    dist = ROOT / "dist"
    if not dist.exists():
        print("  (no dist/ — skipping artifact scan)")
        return findings

    for whl in sorted(dist.glob("*.whl")):
        with zipfile.ZipFile(whl) as z:
            for name in z.namelist():
                findings += scan_text(f"{whl.name}:{name}",
                                      z.read(name).decode("utf-8", "replace"))

    for sd in sorted(dist.glob("*.tar.gz")):
        with tarfile.open(sd) as t:
            for member in t.getmembers():
                if not member.isfile():
                    continue
                if any(bad in "/" + member.name for bad in FORBIDDEN_IN_SDIST):
                    findings.append(
                        f"{sd.name}: operational path must not ship: {member.name}")
                    continue
                handle = t.extractfile(member)
                if handle is None:
                    continue
                findings += scan_text(f"{sd.name}:{member.name}",
                                      handle.read().decode("utf-8", "replace"))
    return findings


def main() -> int:
    findings = scan_tree()
    if "--dist" in sys.argv:
        findings += scan_dist()

    if findings:
        print("SECRET SCAN FAILED\n")
        for f in findings:
            print(f"  {f}")
        print(f"\n{len(findings)} finding(s). Nothing ships until these are gone.")
        return 1

    print("secret scan: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
