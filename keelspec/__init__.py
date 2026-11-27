"""KeelSpec — the rubric, the gate, and the line that builds against them.

Declare your typed product artifacts (features, decisions, terms, rules, whatever
your project needs) in a ``product.config.yaml``; KeelSpec loads them, enforces the
schema + cross-references, compiles a JSON bundle, and fails CI if the committed
bundle drifts — turning a folder of hopeful markdown into code.

Three surfaces, in increasing order of ambition:

* ``build`` / ``validate`` — the compiler and the gate. Deterministic, two
  dependencies, no network. This is what CI runs.
* ``evidence`` — a content-addressed record of what was checked, when, on which
  commit, and with what result.
* ``index`` / ``lsp`` / ``mcp`` — the same validated graph, answered for an editor
  and for an agent. Both delegate every verdict to ``validate``: there is one judge.
* ``orchestration`` — the agent-built lifecycle: Understand → Disambiguate (a
  human gate, signed by named roles) → Design → Develop → Test → adversarial
  Verify → Triage, with bounded repair. ``risk`` decides how much of it a feature
  gets; ``metrics`` adds up what it did. Needs ``keelspec[agents]``; nothing else
  does.

The gate is never an agent. A judge that could be persuaded could not produce
evidence, so every station past it is deterministic or human by construction.
"""
from __future__ import annotations

from .config import ArtifactType, Config, Delivery, Reference, RiskTier, load_config
from .diagnostics import CODES, Diagnostic, Report, register
from .engine import build, load, render_bundle, validate
from .evidence import build_record
from .evidence import render as render_evidence
from .evidence import verify as verify_evidence
from .index import Artifact, Edge, Location, ProductIndex
from .orchestration import (
    CLEAN_SCHEMA,
    LENS_NAMES,
    LENSES,
    ROSTER,
    TRIAGE_SCHEMA,
    Orchestrator,
    Runner,
    RunReport,
    Station,
    StubRunner,
    Verdict,
    read_approvals,
    read_resolutions,
    save_report,
    write_questions,
)
from .plugin import Registry, load_plugin
from .risk import Assessment, assess

__version__ = "1.0.1"

__all__ = [
    # the agent-built lifecycle
    "CLEAN_SCHEMA",
    # diagnostics
    "CODES",
    "LENSES",
    "LENS_NAMES",
    "ROSTER",
    "TRIAGE_SCHEMA",
    # the resolved graph, with positions
    "Artifact",
    # config
    "ArtifactType",
    "Assessment",
    "Config",
    "Delivery",
    "Diagnostic",
    "Edge",
    "Location",
    "Orchestrator",
    "ProductIndex",
    "Reference",
    # plugins
    "Registry",
    "Report",
    "RiskTier",
    "RunReport",
    "Runner",
    "Station",
    "StubRunner",
    "Verdict",
    "__version__",
    "assess",
    # engine
    "build",
    # evidence
    "build_record",
    "load",
    "load_config",
    "load_plugin",
    "read_approvals",
    "read_resolutions",
    "register",
    "render_bundle",
    "render_evidence",
    "save_report",
    "validate",
    "verify_evidence",
    "write_questions",
]
