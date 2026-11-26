"""Named bundles of artifact types a project opts into with one config line.

    presets: [agents]

expands, before validation, into the types below. They are ordinary KeelSpec types:
the same loader, the same PAC-001..PAC-060 checks, the same LSP completion and MCP
tools. What a preset adds beyond the types is a set of library-owned checks (for
``agents``: PAC-070..PAC-077 in ``keelspec.agents``), run only when it is enabled.

A project that does not list a preset sees no change at all.
"""
from __future__ import annotations

from typing import Any

AGENTS: list[dict[str, Any]] = [
    {
        "name": "agents",
        "dir": "agents",
        "id_prefix": "AGENT-",
        "required": ["id", "title", "purpose", "concept", "criticality", "tools", "policies"],
        "fields": ["title", "purpose", "concept", "criticality", "tools", "policies",
                   "grounding", "scenarios", "owner", "budgets", "model_hints", "status"],
        "enums": {
            "criticality": ["low", "medium", "high"],
            "status": ["idea", "building", "simulated", "deployed", "retired"],
        },
        "references": [
            {"field": "tools", "to": "tools"},
            {"field": "policies", "to": "policies"},
            {"field": "grounding", "to": ["rules", "constraints", "terms"]},
            {"field": "scenarios", "to": "scenarios"},
        ],
    },
    {
        "name": "tools",
        "dir": "tools",
        "id_prefix": "TOOL-",
        "required": ["id", "title", "transport", "server", "operations", "data_classes"],
        "fields": ["title", "transport", "server", "operations", "data_classes",
                   "side_effects", "timeout_seconds", "max_result_bytes", "owner", "status"],
        "enums": {
            "transport": ["stdio", "http"],
            "side_effects": ["none", "read", "write", "money"],
            "status": ["idea", "building", "deployed", "retired"],
        },
    },
    {
        "name": "policies",
        "dir": "policies",
        "id_prefix": "POL-",
        "required": ["id", "title", "effect", "match"],
        "fields": ["title", "effect", "match", "when", "approvers", "rationale", "references"],
        "enums": {"effect": ["deny", "require_approval", "allow", "redact"]},
        "references": [
            {"field": "references", "to": ["rules", "constraints", "decisions"]},
        ],
    },
    {
        "name": "scenarios",
        "dir": "scenarios",
        "id_prefix": "SCN-",
        "required": ["id", "title", "agent", "input", "fixtures", "expect"],
        "fields": ["title", "agent", "input", "fixtures", "expect", "tags"],
        "references": [{"field": "agent", "to": "agents"}],
    },
]

PRESETS: dict[str, list[dict[str, Any]]] = {"agents": AGENTS}


def expand(data: dict) -> dict:
    """Return config data with every listed preset's types appended.

    A project type with the same name as a preset type is an error, not an override:
    the library's checks rely on the preset's shape, and a silent override would let
    them run against a schema they were not written for.
    """
    names = data.get("presets") or []
    if not names:
        return data
    unknown = [n for n in names if n not in PRESETS]
    if unknown:
        raise ValueError(f"unknown preset(s) {unknown}; known: {sorted(PRESETS)}")
    types = list(data.get("types") or [])
    declared = {t.get("name") for t in types if isinstance(t, dict)}
    for name in names:
        for t in PRESETS[name]:
            if t["name"] in declared:
                raise ValueError(
                    f"type '{t['name']}' is declared in product.config.yaml and also "
                    f"provided by preset '{name}'; remove one of them")
            types.append({k: (list(v) if isinstance(v, list) else v) for k, v in t.items()})
            declared.add(t["name"])
    return {**data, "types": types}
