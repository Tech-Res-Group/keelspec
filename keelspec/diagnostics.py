"""Stable diagnostic codes — the validator's public API.

Every validation error carries a stable ``PAC-NNN`` code, prepended to a human
message. Codes are an API: CI, dashboards, and humans refer to a *class* of failure
without matching on prose. **Never renumber an existing code** — retire it and add a
new one. Ranges mirror the original product-as-code design:

  * ``00x`` — required-field / schema
  * ``01x`` — id & graph integrity (prefix, filename, duplicates)
  * ``02x`` — cross-reference resolution
  * ``03x`` — enum / allowed-value
  * ``06x`` — generated-bundle staleness

Projects add their own checks (see ``hooks``) and register custom codes via
``register()`` — keep them in a project-specific range (e.g. ``9xx``) so they never
collide with the core set.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

# ── core code registry ───────────────────────────────────────────────────────
CODES: dict[str, str] = {
    "PAC-001": "artifact is missing a required field",
    "PAC-010": "artifact id does not start with its type's id_prefix",
    "PAC-011": "artifact id does not match its filename",
    "PAC-012": "duplicate artifact id within a type",
    "PAC-020": "a reference field does not resolve to a known artifact",
    "PAC-030": "a field value is not in the type's allowed set",
    "PAC-060": "the committed generated bundle is missing or stale",
}


def register(code: str, message: str) -> None:
    """Register (or re-document) a diagnostic code. A project owns its own code
    numbers — re-registering an existing code overrides its documentation, so a
    project that reuses the core numbers with its own meanings (or ships its own
    range) just works."""
    CODES[code] = message


@dataclass(frozen=True)
class Diagnostic:
    """A single finding: a stable code, a human message, and where it was found.

    ``field`` and ``value`` narrow "where" from a file to a point inside it: which
    frontmatter key the finding is about, and which of that key's values offended.
    Both are optional and empty by default, so a plugin validator written against
    the old three-argument :meth:`Report.add` keeps working unchanged.

    They exist because an editor needs to underline a range, and the alternative is
    recovering the field by pattern-matching ``message`` — which is exactly what
    stable codes exist to stop consumers doing. A structured field is cheap here and
    unreliable everywhere else.
    """

    code: str
    message: str
    where: str = ""
    severity: str = "error"  # "error" (gating) or "warning" (advisory)
    field: str = ""  # the frontmatter key this is about, when the check knows it
    value: str = ""  # the offending value within that key, when there is one

    def render(self) -> str:
        loc = f"{self.where}: " if self.where else ""
        return f"{self.code} {loc}{self.message}"


@dataclass
class Report:
    """Accumulates diagnostics from a validation run."""

    # `dataclasses.field` spelled out: `Diagnostic` above has an attribute *named*
    # `field`, and a bare `field(...)` here would read as that to anyone skimming.
    diagnostics: list[Diagnostic] = dataclasses.field(default_factory=list)

    def add(
        self,
        code: str,
        message: str,
        where: str = "",
        severity: str = "error",
        *,
        field: str = "",
        value: str = "",
    ) -> None:
        self.diagnostics.append(Diagnostic(code, message, where, severity, field, value))

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors
