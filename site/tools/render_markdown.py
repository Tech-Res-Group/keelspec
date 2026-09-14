"""Emit a markdown rendition of every page, for agents that ask for one.

An agent reading this site gets ~26% signal and ~74% navigation, chrome and styling
hooks. Markdown is what it actually wants: the same content, none of the wrapper,
a fraction of the tokens.

Caddy serves these on `Accept: text/markdown` (see the Caddyfile), which is the
acceptmarkdown.com convention. `Vary: Accept` goes with it — without that header a
CDN will happily hand the cached HTML to an agent asking for markdown, or the
reverse, depending on which variant landed in the cache first.

Blog posts are converted from the HTML rather than copied from `content/posts/`
on purpose: the rendition should match what a human sees at that URL, including
the summary and related links the renderer adds.

    python tools/render_markdown.py
"""
from __future__ import annotations

import html
import html.parser
import pathlib
import re

PUBLIC = pathlib.Path(__file__).resolve().parent.parent / "public"
SKIP = {"carousel.html", "og.html"}


class _AriaHiddenStripper(html.parser.HTMLParser):
    """Remove aria-hidden subtrees, tracking nesting depth.

    A non-greedy regex closes at the first inner `</div>`, so the decorative station
    rail survived with only its wrapper removed. Nesting needs a parser, not a
    pattern.
    """

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
            "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self._skip_depth: int | None = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        hidden = dict(attrs).get("aria-hidden") == "true"
        if tag in self.VOID:
            if self._skip_depth is None and not hidden:
                self.out.append(self.get_starttag_text() or "")
            return
        self._depth += 1
        if hidden and self._skip_depth is None:
            self._skip_depth = self._depth
            return
        if self._skip_depth is None:
            self.out.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if self._skip_depth is not None and self._depth == self._skip_depth:
            self._skip_depth = None
            self._depth -= 1
            return
        if self._skip_depth is None:
            self.out.append(f"</{tag}>")
        self._depth -= 1

    def handle_data(self, data):
        if self._skip_depth is None:
            self.out.append(data)

    def handle_entityref(self, name):
        if self._skip_depth is None:
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if self._skip_depth is None:
            self.out.append(f"&#{name};")


def _drop_aria_hidden(source: str) -> str:
    """Anything marked aria-hidden is decorative by the author's own declaration --
    the station rail, for instance. A screen reader skips it; so should an agent."""
    stripper = _AriaHiddenStripper()
    stripper.feed(source)
    return "".join(stripper.out)


def _strip(fragment: str) -> str:
    """Inline HTML -> inline markdown."""
    out = fragment
    out = re.sub(r"<br\s*/?>", "\n", out, flags=re.I)
    out = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", out, flags=re.S | re.I)
    out = re.sub(r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", out, flags=re.S | re.I)
    out = re.sub(r"<(em|i)[^>]*>(.*?)</\1>", r"*\2*", out, flags=re.S | re.I)
    out = re.sub(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"[\2](\1)", out, flags=re.S | re.I)
    out = re.sub(r"<[^>]+>", "", out)
    out = html.unescape(out)
    return re.sub(r"[ \t]+", " ", out).strip()


def to_markdown(source: str) -> str:
    """A deliberately small HTML -> markdown pass over our own generated pages.

    It does not need to handle arbitrary HTML — only the shapes these generators
    produce — so it stays readable instead of pulling in a dependency.
    """
    body = source
    # drop everything an agent should not have to read
    body = re.sub(r"(?is)<head.*?</head>", "", body)
    for tag in ("script", "style", "svg", "nav", "footer", "form"):
        body = re.sub(rf"(?is)<{tag}\b.*?</{tag}>", "", body)
    body = _drop_aria_hidden(body)

    blocks: list[str] = []
    pattern = re.compile(
        r"(?is)<(h1|h2|h3|h4|p|pre|ul|ol|blockquote)\b[^>]*>(.*?)</\1>")

    for match in pattern.finditer(body):
        tag, inner = match.group(1).lower(), match.group(2)

        if tag.startswith("h"):
            level = int(tag[1])
            text = _strip(inner)
            if text:
                blocks.append("#" * level + " " + text)
        elif tag == "pre":
            code = re.sub(r"(?is)</?code[^>]*>", "", inner)
            code = html.unescape(re.sub(r"<[^>]+>", "", code)).strip("\n")
            if code.strip():
                blocks.append("```\n" + code + "\n```")
        elif tag in ("ul", "ol"):
            items = re.findall(r"(?is)<li\b[^>]*>(.*?)</li>", inner)
            marker = "-" if tag == "ul" else "1."
            lines = [f"{marker} {_strip(i)}" for i in items if _strip(i)]
            if lines:
                blocks.append("\n".join(lines))
        elif tag == "blockquote":
            text = _strip(inner)
            if text:
                blocks.append("> " + text.replace("\n", "\n> "))
        else:
            text = _strip(inner)
            if text:
                blocks.append(text)

    # collapse the duplicate headings our section markup sometimes produces
    deduped: list[str] = []
    for block in blocks:
        if not deduped or block != deduped[-1]:
            deduped.append(block)
    return "\n\n".join(deduped).strip() + "\n"


def front_matter(source: str, url: str) -> str:
    title = re.search(r"(?is)<title>(.*?)</title>", source)
    desc = re.search(r'(?is)<meta\s+name="description"\s+content="(.*?)"', source)
    lines = ["---"]
    if title:
        lines.append(f"title: {html.unescape(_strip(title.group(1)))}")
    if desc:
        lines.append(f"description: {html.unescape(desc.group(1))}")
    lines += [f"url: https://keelspec.com{url}", "---", ""]
    return "\n".join(lines)


def main() -> int:
    pages = [p for p in sorted(PUBLIC.rglob("*.html")) if p.name not in SKIP]
    written = 0
    for page in pages:
        source = page.read_text(encoding="utf-8")
        rel = "/" + page.relative_to(PUBLIC).as_posix()
        url = rel[: -len("index.html")] if rel.endswith("/index.html") else rel
        body = to_markdown(source)
        if len(body) < 80:                       # nothing worth serving
            continue
        target = page.with_suffix(".md")
        target.write_text(front_matter(source, url) + body,
                          encoding="utf-8", newline="\n")
        written += 1

    print(f"wrote {written} markdown rendition(s) beside {len(pages)} page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
