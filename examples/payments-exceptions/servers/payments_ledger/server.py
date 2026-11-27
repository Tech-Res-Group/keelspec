"""MCP server for TOOL-payments-ledger: Payments ledger (read).

Scaffolded by `keelspec tools scaffold TOOL-payments-ledger`, then filled in. A
reference server for the example: it reads fixtures/payments.json, never a real
ledger. The tool names must stay equal to the artifact's operations (PAC-073);
test_server.py checks that.
"""
from __future__ import annotations

import json
import pathlib

try:
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer
    from mcp.server.fastmcp.exceptions import ToolError

DATA = pathlib.Path(__file__).resolve().parents[2] / "fixtures" / "payments.json"

server = MCPServer("TOOL-payments-ledger")


def _payment(end_to_end_id: str) -> dict:
    payments = json.loads(DATA.read_text(encoding="utf-8"))
    if end_to_end_id not in payments:
        raise ToolError(f"no payment with end-to-end id {end_to_end_id}")
    return payments[end_to_end_id]


@server.tool()
def get_payment(end_to_end_id: str) -> dict:
    """The original payment instruction (pacs.008) by end-to-end id.

    Side effects: read.
    """
    return {k: v for k, v in _payment(end_to_end_id).items() if k != "postings"}


@server.tool()
def list_postings(end_to_end_id: str) -> dict:
    """Ledger postings for a payment, oldest first, with whether each settled.

    Side effects: read.
    """
    return {"end_to_end_id": end_to_end_id, "postings": _payment(end_to_end_id)["postings"]}


if __name__ == "__main__":
    server.run()
