"""``keelspec mcp`` — the product graph as tools, for the agent that writes into it.

In a repo run this way, the author of ``product/features/refunds.md`` is increasingly
a model rather than a cursor. It faces the same problem the editor solves and has a
worse time of it: asked for a ``constraints`` list it will happily invent
``CON-refund-window``, because a plausible id is exactly what a language model is
good at producing. The graph knows which ids exist. This hands it over.

**Read-only, on purpose.** Nothing here writes an artifact, edits a file, or reports
a verdict of its own. An agent proposes with its own tools and this tells it the
truth about the tree — including, via ``validate``, what the gate currently says.
A server that could also write would let the thing being judged edit the evidence,
and the project's whole claim is that the judge cannot be persuaded.

The tool bodies are plain functions over :class:`~keelspec.index.ProductIndex`, and
:func:`serve` does the protocol wiring — so they are testable without the SDK
installed, the same split as the language server.

    pip install 'keelspec[mcp]'
    keelspec mcp                 # speaks MCP on stdio
"""
from __future__ import annotations

import pathlib

from .index import ProductIndex


def schema(index: ProductIndex) -> list[dict]:
    """The declared artifact types: what a file of each kind must contain.

    The first thing to ask before writing an artifact, and the answer that stops an
    agent guessing at a schema it could have read.
    """
    out = []
    for t in index.config.types:
        out.append(
            {
                "type": t.name,
                "directory": f"{index.config.product_dir}/{t.dir}/",
                "id_prefix": t.id_prefix or "",
                "id_matches_filename": t.id_matches_filename,
                "required_fields": list(t.required),
                "fields": list(t.fields),
                "enums": {k: list(v) for k, v in t.enums.items()},
                "references": [
                    {"field": r.field, "must_resolve_to": r.to} for r in t.references
                ],
                "count": len(index.of_type(t.name)),
            }
        )
    return out


def list_artifacts(index: ProductIndex, type_name: str = "") -> list[dict]:
    """Every artifact, or every artifact of one type: id, title, path."""
    arts = index.of_type(type_name) if type_name else list(index.artifacts.values())
    return [
        {"id": a.id, "type": a.type_name, "title": a.title(), "path": a.path}
        for a in sorted(arts, key=lambda a: (a.type_name, a.id))
    ]


def get_artifact(index: ProductIndex, artifact_id: str, type_name: str = "") -> dict:
    """One artifact in full, with both directions of its edges."""
    found = index.find(artifact_id) if not type_name else [
        a for a in [index.get(artifact_id, type_name)] if a
    ]
    if not found:
        return {"error": f"no artifact with id '{artifact_id}'", "id": artifact_id}
    out = []
    for a in found:
        fields = {k: v for k, v in a.record.items() if k not in ("_file", "body")}
        out.append(
            {
                "id": a.id,
                "type": a.type_name,
                "path": a.path,
                "fields": fields,
                "body": a.record.get("body", ""),
                "references": [
                    {"field": e.field, "target": e.target_id, "target_type": e.target_type}
                    for e in index.outgoing(a.id, a.type_name)
                ],
                "referenced_by": [
                    {"source": e.source_id, "source_type": e.source_type, "field": e.field}
                    for e in index.references_to(a.id, a.type_name)
                ],
            }
        )
    return out[0] if len(out) == 1 else {"id": artifact_id, "matches": out}


def allowed_values(index: ProductIndex, type_name: str, field_name: str) -> dict:
    """What may legally go in one field — the answer that prevents an invented id.

    Empty ``values`` with ``closed: false`` means the field is free text; the gate
    has no opinion about it.
    """
    values = index.allowed_values(type_name, field_name)
    target = index.target_type(type_name, field_name)
    t = index.config.type_by_name(type_name)
    return {
        "type": type_name,
        "field": field_name,
        "closed": bool(values),
        "kind": "enum" if (t and field_name in t.enums) else ("reference" if target else "free"),
        "must_resolve_to": target,
        "values": values,
    }


def references_to(index: ProductIndex, artifact_id: str, type_name: str = "") -> dict:
    """What points at this artifact — i.e. what breaks if it changes or retires."""
    edges = index.references_to(artifact_id, type_name)
    return {
        "id": artifact_id,
        "referenced_by_count": len(edges),
        "referenced_by": [
            {"source": e.source_id, "source_type": e.source_type, "field": e.field}
            for e in edges
        ],
    }


def validate(index: ProductIndex) -> dict:
    """Run the gate and report it verbatim — the same call CI makes.

    An agent that has just written an artifact can find out whether it holds before a
    human is asked to look at it. The verdict is the engine's; nothing here softens
    a finding or decides that an error is really a warning.
    """
    findings = index.diagnostics()
    errors = [d for d in findings if d.severity == "error"]
    return {
        "result": "pass" if not errors else "fail",
        "errors": len(errors),
        "warnings": len(findings) - len(errors),
        "findings": [
            {
                "code": d.code,
                "severity": d.severity,
                "where": d.where,
                "field": d.field,
                "value": d.value,
                "message": d.message,
            }
            for d in findings
        ],
    }


def agent_card(index: ProductIndex, agent_id: str) -> dict:
    """An agent, resolved: its instructions, grounding, tools with their operations,
    policies and scenarios. What the runtime would assemble, without running it."""
    art = index.get(agent_id, "agents")
    if art is None:
        return {"error": f"no agent {agent_id!r}"}
    rec = art.record

    def records(type_name: str, ids) -> list[dict]:
        """Resolve ids to records; with no type (grounding spans several), by id alone."""
        out = []
        for i in ids or []:
            found = index.get(i, type_name) if type_name else next(iter(index.find(i)), None)
            if found is not None:
                out.append(found.record)
        return out

    from .agents import operations, side_effects_of
    tools = [{"id": t["id"], "title": t.get("title"),
              "operations": [{"name": op, "side_effects": side_effects_of(t, op)}
                             for op in operations(t)],
              "data_classes": t.get("data_classes")}
             for t in records("tools", rec.get("tools"))]
    return {
        "id": agent_id,
        "title": rec.get("title"),
        "purpose": rec.get("purpose"),
        "concept": rec.get("concept"),
        "criticality": rec.get("criticality"),
        "instructions": rec.get("body", ""),
        "grounding": [{"id": g["id"], "title": g.get("title") or g.get("term"),
                       "text": g.get("statement") or g.get("definition") or g.get("body")}
                      for g in records("", rec.get("grounding"))],
        "tools": tools,
        "policies": [{"id": p["id"], "effect": p.get("effect"), "match": p.get("match"),
                      "when": p.get("when")} for p in records("policies", rec.get("policies"))],
        "scenarios": list(rec.get("scenarios") or []),
        "budgets": rec.get("budgets"),
    }


def policy_explain(index: ProductIndex, agent_id: str, tool_id: str, operation: str,
                   args: dict | None = None) -> dict:
    """The policy decision for a hypothetical call. Executes nothing."""
    from .runtime.policy import explain
    bundle: dict[str, list[dict]] = {}
    for (type_name, _), art in index.artifacts.items():
        bundle.setdefault(type_name, []).append(art.record)
    try:
        return explain(bundle, agent_id, tool_id, operation, args or {})
    except KeyError as exc:
        return {"error": str(exc).strip("'\"")}


# ── the protocol wiring ──────────────────────────────────────────────────────
def serve(  # pragma: no cover - protocol glue; needs the optional mcp extra
    config_path: str = "product.config.yaml", root: str = ".", plugin: str | None = None
) -> int:
    """Serve the graph over MCP on stdio until the client disconnects."""
    try:
        # Absolute import: this module is `keelspec.mcp`, the SDK is top-level `mcp`,
        # and Python 3 resolves this to the latter.
        try:
            from mcp.server.mcpserver import MCPServer as FastMCP  # mcp 2.x
        except ImportError:
            from mcp.server.fastmcp import FastMCP  # mcp 1.x
    except ImportError:  # pragma: no cover - depends on an optional extra
        import sys

        print(
            "keelspec mcp needs the MCP extra:\n\n    pip install 'keelspec[mcp]'\n",
            file=sys.stderr,
        )
        return 2

    from .config import load_config
    from .plugin import load_plugin

    root_path = pathlib.Path(root).resolve()
    cfg = pathlib.Path(config_path)
    cfg_path = cfg if cfg.is_absolute() else root_path / cfg

    def index() -> ProductIndex:
        """Rebuilt per call: an agent edits the tree between them, and a cached
        graph would answer questions about the tree as it used to be."""
        return ProductIndex.build(load_config(cfg_path), root_path, load_plugin(plugin))

    server = FastMCP("keelspec")

    @server.tool()
    def product_schema() -> list[dict]:
        """The declared artifact types: directories, required fields, enums, and which
        fields are cross-references that must resolve. Read this before authoring."""
        return schema(index())

    @server.tool()
    def product_list(type_name: str = "") -> list[dict]:
        """List artifacts — all of them, or one type's. Returns id, type, title, path."""
        return list_artifacts(index(), type_name)

    @server.tool()
    def product_get(artifact_id: str, type_name: str = "") -> dict:
        """One artifact in full: its fields, body, outgoing references and what points
        at it. Pass type_name when an id is shared by two types."""
        return get_artifact(index(), artifact_id, type_name)

    @server.tool()
    def product_allowed_values(type_name: str, field_name: str) -> dict:
        """The legal values for a field — enum members, or the ids it must resolve to.
        Call this instead of guessing an id."""
        return allowed_values(index(), type_name, field_name)

    @server.tool()
    def product_references_to(artifact_id: str, type_name: str = "") -> dict:
        """Everything that references this artifact — what breaks if it changes."""
        return references_to(index(), artifact_id, type_name)

    @server.tool()
    def product_validate() -> dict:
        """Run the KeelSpec gate over the tree and return its findings verbatim:
        the same PAC-NNN codes, severities and locations CI reports."""
        return validate(index())

    @server.tool()
    def product_agent_card(agent_id: str) -> dict:
        """An agent resolved: instructions, grounding, tools and operations, policies,
        scenarios and budgets. Read-only."""
        return agent_card(index(), agent_id)

    @server.tool()
    def product_policy_explain(agent_id: str, tool_id: str, operation: str,
                               args: dict | None = None) -> dict:
        """Decide a hypothetical tool call with the agent's policies -- allow, redact,
        require_approval or deny, and which policies decided it. Executes nothing."""
        return policy_explain(index(), agent_id, tool_id, operation, args)

    server.run()
    return 0
