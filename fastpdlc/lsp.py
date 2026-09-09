"""``fastpdlc lsp`` — the product graph, in your editor.

Authoring an artifact means writing cross-references by hand: a ``governed_by`` that
must name a real decision, a ``constraints`` list whose every entry must resolve, a
``status`` from a closed set. Today you learn you typed ``CON-residency-pen`` when CI
goes red. The graph already knows the answer at the moment you type it.

**One judge.** Diagnostics here are :func:`fastpdlc.engine.validate`'s, unmodified,
and they are computed from the file *on disk* — the same bytes CI will read. An
editor that validated your unsaved buffer would be a second opinion about
correctness, and a project whose whole claim is a deterministic gate cannot afford
two. Save to re-check; the underlines are then exactly what the gate will say.

Everything else — completion, hover, go-to-definition, find-references — reads the
live buffer for *position* and the index for *meaning*, which is safe: those answer
"what is here?", never "is this allowed?".

The protocol wiring is confined to :func:`serve`. The functions above it are pure —
they take an index, some text and a cursor, and return plain data — so the
interesting logic is testable without a language client or ``pygls`` installed. Same
split as the orchestrator and its runners, for the same reason.

    pip install 'fastpdlc[lsp]'
    fastpdlc lsp                 # speaks LSP on stdio; editors launch this
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass

from .diagnostics import Diagnostic
from .index import KEY, Location, ProductIndex, field_at, frontmatter_bounds, locate, token_at


@dataclass(frozen=True)
class Completion:
    """One offer. ``detail`` is the right-hand hint an editor shows beside the label."""

    label: str
    detail: str = ""
    documentation: str = ""


def _in_frontmatter(lines: list[str], line_no: int) -> bool:
    start, end = frontmatter_bounds(lines)
    return start <= line_no < end


def _is_key_position(line: str, char: int) -> bool:
    """True when the cursor is typing a field name rather than a value.

    A list item (``  - CON-…``) is always a value, even though it has no colon.
    """
    prefix = line[:char]
    return ":" not in prefix and not prefix.lstrip().startswith("-")


def completions_at(index: ProductIndex, rel_path: str, text: str, line_no: int, char: int) -> list[Completion]:
    """What may legally be typed here — field names, or a field's allowed values.

    Everything offered comes from the config the gate reads, so an accepted
    completion cannot be a ``PAC-020`` or a ``PAC-030``.
    """
    type_name = index.type_for_file(rel_path)
    if not type_name:
        return []
    lines = text.splitlines()
    if not (0 <= line_no < len(lines)) or not _in_frontmatter(lines, line_no):
        return []

    if _is_key_position(lines[line_no], char):
        present = {
            m.group(1)
            for i in range(*frontmatter_bounds(lines))
            if i != line_no and (m := KEY.match(lines[i]))
        }
        return [
            Completion(name, f"{type_name} field")
            for name in index.known_fields(type_name)
            if name not in present
        ]

    field_name = field_at(lines, line_no)
    if not field_name:
        return []
    target = index.target_type(type_name, field_name)
    return [
        Completion(
            label=value,
            detail=target or f"{field_name} value",
            documentation=(art.summary() if (art := index.get(value, target)) else ""),
        )
        for value in index.allowed_values(type_name, field_name)
    ]


def _token(text: str, line_no: int, char: int) -> str:
    lines = text.splitlines()
    if not (0 <= line_no < len(lines)):
        return ""
    return token_at(lines[line_no], char)[0]


def hover_at(index: ProductIndex, text: str, line_no: int, char: int) -> str:
    """The card for the id under the cursor — what it means, without leaving the file.

    An id shared by two types (a feature and its spec) renders both. Picking one
    would be a guess, and the ambiguity is itself worth seeing.
    """
    found = index.find(_token(text, line_no, char))
    if not found:
        return ""
    cards = []
    for art in found:
        body = art.summary()
        incoming = index.references_to(art.id, art.type_name)
        if incoming:
            shown = ", ".join(f"`{e.source_id}`" for e in incoming[:8])
            more = f" and {len(incoming) - 8} more" if len(incoming) > 8 else ""
            body += f"\n\nReferenced by {len(incoming)}: {shown}{more}"
        cards.append(body)
    return "\n\n---\n\n".join(cards)


def definition_at(index: ProductIndex, text: str, line_no: int, char: int) -> list[Location]:
    """Where the id under the cursor is declared — plural, when the id is shared."""
    token = _token(text, line_no, char)
    out = []
    for art in index.find(token):
        if art.path:
            out.append(locate(index.root, art.path, "id", token) or Location(art.path, 0, 0, 0))
    return out


def references_at(index: ProductIndex, text: str, line_no: int, char: int) -> list[Location]:
    """Every place that names the id under the cursor, declarations included."""
    token = _token(text, line_no, char)
    found = index.find(token)
    if not found:
        return []

    out: list[Location] = []
    seen: set[tuple[str, int, int]] = set()

    def push(loc: Location | None) -> None:
        if loc and (key := (loc.path, loc.line, loc.col)) not in seen:
            seen.add(key)
            out.append(loc)

    for art in found:
        if art.path:
            push(locate(index.root, art.path, "id", token))
        for edge in index.references_to(art.id, art.type_name):
            source = index.get(edge.source_id, edge.source_type)
            if source and source.path:
                push(locate(index.root, source.path, edge.field, token))
    return out


def diagnostics_by_file(index: ProductIndex) -> dict[str, list[tuple[Location, Diagnostic]]]:
    """The gate's findings, grouped by the file each belongs to.

    Every known artifact file appears, including the clean ones. An editor keeps
    showing the underlines it was last given, so a file that has just been *fixed*
    must be published with an empty list — clearing stale errors matters as much as
    drawing new ones, and only the sender knows a file went quiet.

    Tree-level findings are dropped here. ``PAC-060`` says the committed bundle is
    stale, which is true of the repository and of no particular line in it; hanging
    it on an arbitrary file would blame something innocent.
    """
    grouped: dict[str, list[tuple[Location, Diagnostic]]] = {
        art.path: [] for art in index.artifacts.values() if art.path
    }
    for d in index.diagnostics():
        loc = index.locate_diagnostic(d)
        if loc is None:
            continue
        grouped.setdefault(loc.path, []).append((loc, d))
    return grouped


def symbols(index: ProductIndex, query: str = "") -> list[tuple[str, str, Location]]:
    """``(id, type_name, location)`` for every artifact matching a substring query."""
    q = query.lower()
    out = []
    for art in sorted(index.artifacts.values(), key=lambda a: (a.id, a.type_name)):
        if q and q not in art.id.lower() and q not in art.title().lower():
            continue
        loc = locate(index.root, art.path, "id", art.id) or Location(art.path, 0, 0, 0)
        out.append((art.id, art.type_name, loc))
    return out


# ── the protocol wiring ──────────────────────────────────────────────────────
def serve(  # pragma: no cover - protocol glue; needs the optional pygls extra
    config_path: str = "product.config.yaml", root: str = ".", plugin: str | None = None
) -> int:
    """Run the language server on stdio until the client disconnects."""
    try:
        from lsprotocol import types as lsp
        from pygls.server import LanguageServer
        from pygls.uris import from_fs_path, to_fs_path
    except ImportError:  # pragma: no cover - depends on an optional extra
        import sys

        print(
            "fastpdlc lsp needs the language-server extra:\n\n"
            "    pip install 'fastpdlc[lsp]'\n",
            file=sys.stderr,
        )
        return 2

    from . import __version__
    from .config import load_config
    from .plugin import load_plugin

    root_path = pathlib.Path(root).resolve()
    server = LanguageServer("fastpdlc", __version__)
    state: dict = {"index": None}

    def rel(uri: str) -> str:
        """A workspace-relative, forward-slashed path — the shape the bundle uses."""
        fs = to_fs_path(uri)
        if not fs:
            return ""
        try:
            return str(pathlib.Path(fs).resolve().relative_to(root_path)).replace("\\", "/")
        except ValueError:
            return ""

    def index(refresh: bool = False) -> ProductIndex:
        if refresh or state["index"] is None:
            config = load_config(root_path / config_path if not pathlib.Path(config_path).is_absolute() else config_path)
            state["index"] = ProductIndex.build(config, root_path, load_plugin(plugin))
        return state["index"]

    def to_range(loc: Location):
        return lsp.Range(
            start=lsp.Position(line=loc.line, character=loc.col),
            end=lsp.Position(line=loc.line, character=loc.end_col),
        )

    def to_location(loc: Location):
        return lsp.Location(uri=from_fs_path(str(root_path / loc.path)), range=to_range(loc))

    def publish(refresh: bool = True) -> None:
        """Push the gate's verdict for the whole tree.

        Per-file, because a dangling reference is reported against the file that
        wrote it — and clearing stale underlines matters as much as drawing new ones,
        so every known file is published even when it has nothing wrong with it.
        """
        for path, found in diagnostics_by_file(index(refresh=refresh)).items():
            server.publish_diagnostics(
                from_fs_path(str(root_path / path)),
                [
                    lsp.Diagnostic(
                        range=to_range(loc),
                        message=f"{d.code}: {d.message}",
                        severity=(
                            lsp.DiagnosticSeverity.Warning
                            if d.severity == "warning"
                            else lsp.DiagnosticSeverity.Error
                        ),
                        source="fastpdlc",
                        code=d.code,
                    )
                    for loc, d in found
                ],
            )

    @server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
    def _open(params):  # the unused param is the protocol's signature
        publish()

    @server.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
    def _save(params):
        publish()

    @server.feature(
        lsp.TEXT_DOCUMENT_COMPLETION,
        lsp.CompletionOptions(trigger_characters=[" ", ":", "-", "["]),
    )
    def _complete(params):
        doc = server.workspace.get_text_document(params.text_document.uri)
        offers = completions_at(
            index(), rel(params.text_document.uri), doc.source,
            params.position.line, params.position.character,
        )
        return lsp.CompletionList(
            is_incomplete=False,
            items=[
                lsp.CompletionItem(
                    label=c.label,
                    detail=c.detail,
                    documentation=lsp.MarkupContent(
                        kind=lsp.MarkupKind.Markdown, value=c.documentation
                    ) if c.documentation else None,
                )
                for c in offers
            ],
        )

    @server.feature(lsp.TEXT_DOCUMENT_HOVER)
    def _hover(params):
        doc = server.workspace.get_text_document(params.text_document.uri)
        md = hover_at(index(), doc.source, params.position.line, params.position.character)
        if not md:
            return None
        return lsp.Hover(contents=lsp.MarkupContent(kind=lsp.MarkupKind.Markdown, value=md))

    @server.feature(lsp.TEXT_DOCUMENT_DEFINITION)
    def _definition(params):
        doc = server.workspace.get_text_document(params.text_document.uri)
        locs = definition_at(index(), doc.source, params.position.line, params.position.character)
        return [to_location(loc) for loc in locs] or None

    @server.feature(lsp.TEXT_DOCUMENT_REFERENCES)
    def _references(params):
        doc = server.workspace.get_text_document(params.text_document.uri)
        return [
            to_location(loc)
            for loc in references_at(
                index(), doc.source, params.position.line, params.position.character
            )
        ]

    @server.feature(lsp.WORKSPACE_SYMBOL)
    def _symbols(params):
        return [
            lsp.WorkspaceSymbol(
                name=f"{aid} ({type_name})",
                kind=lsp.SymbolKind.Object,
                location=to_location(loc),
            )
            for aid, type_name, loc in symbols(index(), getattr(params, "query", "") or "")
        ]

    server.start_io()
    return 0
