"""MCP server for TOOL-case-management: Exceptions case management.

Scaffolded by `keelspec tools scaffold TOOL-case-management`, then filled in. A
reference server for the example: cases come from fixtures/cases.json, and
comments, repair proposals and releases live in memory for the life of the process.

`release_funds` is implemented on purpose. The server would do it; the agent's
policy (POL-no-funds-movement) is what stops it. That is the point of the example:
the guarantee lives in the spec, not in the tool.

The tool names must stay equal to the artifact's operations (PAC-073);
test_server.py checks that.
"""
from __future__ import annotations

import itertools
import json
import pathlib

try:
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer
    from mcp.server.fastmcp.exceptions import ToolError

DATA = pathlib.Path(__file__).resolve().parents[2] / "fixtures" / "cases.json"

server = MCPServer("TOOL-case-management")
_ids = itertools.count(1)
_comments: dict[str, list[dict]] = {}
_proposals: dict[str, dict] = {}
_released: dict[str, int] = {}


def _case(case_id: str) -> dict:
    cases = json.loads(DATA.read_text(encoding="utf-8"))
    if case_id not in cases:
        raise ToolError(f"no case {case_id}")
    return cases[case_id]


@server.tool()
def get_case(case_id: str) -> dict:
    """An exception case by id, with the status message that opened it.

    Side effects: read.
    """
    return {**_case(case_id), "comments": _comments.get(case_id, [])}


@server.tool()
def add_comment(case_id: str, text: str) -> dict:
    """Add a finding to the case for the person who reviews it.

    Side effects: write.
    """
    _case(case_id)
    comment = {"id": f"CMT-{next(_ids)}", "text": text}
    _comments.setdefault(case_id, []).append(comment)
    return {"case_id": case_id, "comment_id": comment["id"]}


@server.tool()
def propose_repair(case_id: str, field: str, new_value: str, amount_minor: int) -> dict:
    """Propose a corrected payment for approval. Amounts are integer minor units.

    Side effects: money.
    """
    _case(case_id)
    if not isinstance(amount_minor, int) or amount_minor < 0:
        raise ToolError("amount_minor must be a non-negative integer")
    proposal_id = f"RPR-{next(_ids)}"
    _proposals[proposal_id] = {"case_id": case_id, "field": field, "new_value": new_value,
                               "amount_minor": amount_minor}
    return {"case_id": case_id, "proposal_id": proposal_id, "status": "proposed"}


@server.tool()
def release_funds(case_id: str, amount_minor: int) -> dict:
    """Release held funds for a case.

    Side effects: money.
    """
    _case(case_id)
    _released[case_id] = _released.get(case_id, 0) + int(amount_minor)
    return {"case_id": case_id, "released_minor": _released[case_id]}


if __name__ == "__main__":
    server.run()
