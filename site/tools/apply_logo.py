"""Swap the wordmark-in-a-box for a real mark.

The old logo was a black tile with a speech-bubble tail -- borrowed wholesale from
the reference site and saying nothing about this product. The new mark is a tick
whose two endpoints are graph nodes: a validated graph, in one glyph, legible at
16px. The open node is the artifact you just changed; the green one is the check
that passed.
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

LOGO_SVG = (
    '<svg class="logo-glyph" viewBox="0 0 40 40" aria-hidden="true">'
    '<rect x="1.6" y="1.6" width="36.8" height="36.8" rx="9" fill="#191919"/>'
    '<path d="M10.5 21.5 L17 28 L29.5 12.5" fill="none" stroke="#fbcc00" '
    'stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round"/>'
    '<circle cx="10.5" cy="21.5" r="3.6" fill="#fff"/>'
    '<circle cx="29.5" cy="12.5" r="3.6" fill="#00b67a"/>'
    '</svg>'
)

NEW = f'{LOGO_SVG}<span class="logo-word">KeelSpec</span>'
OLD = '<span class="logo-mark">KeelSpec</span>'

TARGETS = [
    "tools/render_blog.py",
    "api/newsletter.py",
    "public/index.html",
    "public/404.html",
    "public/privacy.html",
]


def main() -> int:
    for rel in TARGETS:
        path = ROOT / rel
        if not path.exists():
            print(f"  skip {rel} (missing)")
            continue
        text = path.read_text(encoding="utf-8")
        if "logo-glyph" in text:
            print(f"  {rel}: already has the new mark")
            continue
        if OLD not in text:
            print(f"  {rel}: old mark not found")
            continue
        path.write_text(text.replace(OLD, NEW), encoding="utf-8", newline="\n")
        print(f"  {rel}: updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
