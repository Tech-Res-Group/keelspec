"""The resolved graph, with positions — what an editor and an agent both need.

:func:`fastpdlc.engine.validate` answers "is this tree correct?". An editor asks
narrower questions about the same graph — *what may go here, what does this id mean,
who else points at it, and where exactly is the offending text* — and so does an
agent authoring an artifact. Answering them twice, once in ``lsp`` and once in
``mcp``, would be two implementations of the same lookups drifting apart. So they
live here, once, and both surfaces stay thin.

Positions come from a text scan of the frontmatter rather than from the YAML parse,
because a parser gives you values and an editor needs offsets. The scan is bounded to
the frontmatter block: a ``status:`` mentioned in the prose body is not the field.

Nothing here validates. :meth:`ProductIndex.diagnostics` delegates to the engine, so
an editor and CI cannot disagree about what counts as an error — there is one judge,
which is the property the whole project rests on.
"""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field

from .config import Config
from .diagnostics import Diagnostic
from .engine import load, validate

# An id-ish token: what an artifact id can contain, so a cursor anywhere inside
# `CON-residency-pin` or `moneypath.verify` picks up the whole thing.
TOKEN = re.compile(r"[A-Za-z0-9_.:/\-]+")
# A top-level frontmatter key. Nested keys are indented and deliberately excluded:
# the field owning a nested line is the unindented one above it.
KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_.\-]*)\s*:")


@dataclass(frozen=True)
class Location:
    """A range inside a file, zero-based, in the shape an editor wants."""

    path: str  # repo-relative, forward slashes
    line: int
    col: int
    end_col: int


@dataclass(frozen=True)
class Artifact:
    """One record, plus the two things the bundle does not carry: its type and file."""

    id: str
    type_name: str
    path: str
    record: dict

    def title(self) -> str:
        """The most title-like field this artifact has, for a one-line summary."""
        for key in ("title", "term", "label", "name", "statement", "definition"):
            v = self.record.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return self.id

    def summary(self) -> str:
        """Markdown for a hover card: what this id is, and the sentence that says so."""
        lines = [f"**{self.id}** — `{self.type_name}`", "", self.title()]
        # The payload field. A rule's `statement` and a term's `definition` are the
        # thing itself, not metadata about it — a card that shows a rule's title and
        # not its invariant has answered the wrong question.
        for key in ("statement", "definition"):
            v = self.record.get(key)
            if isinstance(v, str) and v.strip() and v.strip() != self.title():
                lines += ["", v.strip()]
        facts = [
            f"- `{key}`: {self.record[key]}"
            for key in ("status", "kind", "owner", "date")
            if self.record.get(key)
        ]
        if facts:
            lines += ["", *facts]
        body = (self.record.get("body") or "").strip()
        if body:
            first = body.split("\n\n", 1)[0].strip()
            lines += ["", first[:400] + ("…" if len(first) > 400 else "")]
        lines += ["", f"`{self.path}`"]
        return "\n".join(lines)


# ── frontmatter scanning ─────────────────────────────────────────────────────
def frontmatter_bounds(lines: list[str]) -> tuple[int, int]:
    """The half-open line range of the frontmatter block, or ``(0, 0)`` if there is none.

    Matches :func:`fastpdlc.engine.parse_frontmatter`'s view of a file: a leading
    ``---`` and everything up to the next one.
    """
    if not lines or lines[0].strip() != "---":
        return (0, 0)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return (1, i)
    return (0, 0)


def field_at(lines: list[str], line_no: int) -> str:
    """Which top-level frontmatter key owns ``line_no``.

    A value on its own line (a list item, a nested mapping) belongs to the nearest
    unindented key above it — which is how ``constraints:`` claims the ``- CON-…``
    lines beneath it.
    """
    start, end = frontmatter_bounds(lines)
    if not (start <= line_no < end):
        return ""
    for i in range(line_no, start - 1, -1):
        m = KEY.match(lines[i])
        if m:
            return m.group(1)
    return ""


def token_at(line: str, char: int) -> tuple[str, int, int]:
    """The id-ish token under a cursor, with its column range. Empty when on space."""
    for m in TOKEN.finditer(line):
        if m.start() <= char <= m.end():
            return (m.group(0), m.start(), m.end())
    return ("", 0, 0)


def locate(
    root: pathlib.Path, rel_path: str, field_name: str = "", value: str = ""
) -> Location | None:
    """Find ``field_name`` (and optionally ``value`` under it) in a file's frontmatter.

    Degrades generously rather than failing: a value whose field is unknown is
    searched for across the block, and a field whose value cannot be found lands on
    the key. An editor underlining the right line and the wrong column is useful; an
    editor that gives up is not.
    """
    try:
        lines = (root / rel_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    start, end = frontmatter_bounds(lines)
    if start == end:
        return None

    key_line = -1
    if field_name:
        for i in range(start, end):
            m = KEY.match(lines[i])
            if m and m.group(1) == field_name:
                key_line = i
                break
        if key_line < 0:
            return None

    if value:
        # The key's own line first, then the indented block beneath it. With no field
        # to anchor to, scan the whole frontmatter.
        scan = range(key_line, end) if key_line >= 0 else range(start, end)
        for i in scan:
            if key_line >= 0 and i > key_line and KEY.match(lines[i]):
                break  # left this key's block
            col = lines[i].find(value)
            if col >= 0:
                return Location(rel_path, i, col, col + len(value))

    if key_line >= 0:
        return Location(rel_path, key_line, 0, len(KEY.match(lines[key_line]).group(1)))
    return None


# ── the index ────────────────────────────────────────────────────────────────
@dataclass
class Edge:
    """One declared reference, typed at both ends.

    Both ends carry a type because an id is unique only *within* a type — that is
    what ``PAC-012`` says, and a graph keyed on the bare id quietly merges a feature
    with the spec that shares its name.
    """

    source_type: str
    source_id: str
    field: str
    target_type: str
    target_id: str


@dataclass
class ProductIndex:
    """Every artifact, every edge, and the config that defines them."""

    config: Config
    root: pathlib.Path
    registry: object = None
    # Keyed by (type_name, id): the only key that is actually unique.
    artifacts: dict[tuple[str, str], Artifact] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    load_error: str = ""

    @classmethod
    def build(cls, config: Config, root: str | pathlib.Path = ".", registry=None) -> ProductIndex:
        idx = cls(config=config, root=pathlib.Path(root), registry=registry)
        try:
            bundle = load(config, root)
        except Exception as exc:  # malformed YAML in one file must not blind the rest
            idx.load_error = str(exc)
            return idx
        for type_name, records in bundle.items():
            for rec in records:
                rid = rec.get("id")
                if rid:
                    idx.artifacts[(type_name, str(rid))] = Artifact(
                        id=str(rid),
                        type_name=type_name,
                        path=rec.get("_file", ""),
                        record=rec,
                    )
        for type_ in config.types:
            for ref in type_.references:
                for rec in bundle.get(type_.name, []):
                    raw = rec.get(ref.field)
                    values = raw if isinstance(raw, list) else [raw] if raw else []
                    for v in values:
                        idx.edges.append(
                            Edge(type_.name, str(rec.get("id")), ref.field, ref.to, str(v))
                        )
        return idx

    # ── lookups ──────────────────────────────────────────────────────────────
    def get(self, artifact_id: str, type_name: str = "") -> Artifact | None:
        """One artifact. Without a type, this is only unambiguous if the id is."""
        if type_name:
            return self.artifacts.get((type_name, artifact_id))
        found = self.find(artifact_id)
        return found[0] if len(found) == 1 else None

    def find(self, artifact_id: str) -> list[Artifact]:
        """Every artifact carrying this id — more than one when types share a name.

        A cursor gives you a token, not a type, so the honest answer here is a list.
        In ``product/`` trees that pair a feature with a spec of the same name, it
        routinely has two entries and both are worth showing.
        """
        return [a for (_, aid), a in self.artifacts.items() if aid == artifact_id]

    def of_type(self, type_name: str) -> list[Artifact]:
        return [a for (tn, _), a in self.artifacts.items() if tn == type_name]

    def type_for_file(self, rel_path: str) -> str:
        """Which configured type a file belongs to, by its directory."""
        norm = rel_path.replace("\\", "/")
        for t in self.config.types:
            if f"/{self.config.product_dir}/{t.dir}/" in f"/{norm}":
                return t.name
        return ""

    def target_type(self, type_name: str, field_name: str) -> str:
        """The type a reference field must resolve to, or '' if it is not an edge."""
        t = self.config.type_by_name(type_name)
        if not t:
            return ""
        for ref in t.references:
            if ref.field == field_name:
                return ref.to
        return ""

    def allowed_values(self, type_name: str, field_name: str) -> list[str]:
        """What may legally go in this field: enum members, or ids of the target type.

        The completion list, derived from the same config the gate reads — so an
        editor can only ever offer something that validates.
        """
        t = self.config.type_by_name(type_name)
        if not t:
            return []
        if field_name in t.enums:
            return list(t.enums[field_name])
        to = self.target_type(type_name, field_name)
        if to:
            return sorted(a.id for a in self.of_type(to))
        return []

    def known_fields(self, type_name: str) -> list[str]:
        """Every frontmatter key this type captures — the key-position completion."""
        t = self.config.type_by_name(type_name)
        if not t:
            return []
        return sorted({"id", *t.fields, *t.required})

    def references_to(self, artifact_id: str, type_name: str = "") -> list[Edge]:
        """Reverse edges: everything pointing at this artifact.

        "What breaks if I retire this rule?" has no cheap answer without them. Pass
        ``type_name`` when you know which of two same-named artifacts you mean.
        """
        return sorted(
            (
                e
                for e in self.edges
                if e.target_id == artifact_id and (not type_name or e.target_type == type_name)
            ),
            key=lambda e: (e.source_type, e.source_id, e.field),
        )

    def outgoing(self, artifact_id: str, type_name: str = "") -> list[Edge]:
        """Every edge this artifact declares."""
        return sorted(
            (
                e
                for e in self.edges
                if e.source_id == artifact_id and (not type_name or e.source_type == type_name)
            ),
            key=lambda e: (e.field, e.target_id),
        )

    # ── validation, delegated ────────────────────────────────────────────────
    def diagnostics(self) -> list[Diagnostic]:
        """The engine's findings. One judge, so an editor and CI cannot disagree."""
        return validate(self.config, self.root, self.registry).diagnostics

    def locate_diagnostic(self, d: Diagnostic) -> Location | None:
        """Where in the tree to underline a finding.

        A ``PAC-001`` is the one finding whose field is, by definition, not in the
        file — so there is no key to point at. It anchors to the frontmatter opener
        instead: an underline on the right file beats no underline at all.
        """
        if not d.where:
            return None  # tree-level, e.g. PAC-060: no file to blame
        if loc := locate(self.root, d.where, d.field, d.value):
            return loc
        return Location(d.where, 0, 0, 3) if (self.root / d.where).exists() else None
