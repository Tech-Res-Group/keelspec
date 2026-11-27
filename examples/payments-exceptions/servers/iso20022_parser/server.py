"""MCP server for TOOL-iso20022-parser: ISO 20022 message parser.

Scaffolded by `keelspec tools scaffold TOOL-iso20022-parser`, then filled in. Pure:
it parses the message it is given and looks codes up in fixtures/reason_codes.json.
The tool names must stay equal to the artifact's operations (PAC-073);
test_server.py checks that.
"""
from __future__ import annotations

import json
import pathlib
import xml.etree.ElementTree as ET
from decimal import Decimal

try:
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer
    from mcp.server.fastmcp.exceptions import ToolError

CODES = pathlib.Path(__file__).resolve().parents[2] / "fixtures" / "reason_codes.json"
MAX_MESSAGE_BYTES = 256 * 1024

server = MCPServer("TOOL-iso20022-parser")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first(root: ET.Element, name: str) -> ET.Element | None:
    return next((e for e in root.iter() if _local(e.tag) == name), None)


def _text(root: ET.Element, name: str) -> str | None:
    el = _first(root, name)
    return el.text.strip() if el is not None and el.text else None


@server.tool()
def parse_message(xml: str) -> dict:
    """Parse a pacs.008 or pacs.002 message into its key fields.

    Side effects: none.
    """
    if len(xml.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ToolError("message too large")
    if "<!DOCTYPE" in xml or "<!ENTITY" in xml:
        raise ToolError("DTDs and entities are not accepted")
    root = ET.fromstring(xml)
    namespace = root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else ""
    kind = namespace.rsplit(":", 1)[-1] if namespace else _local(root.tag)
    if _first(root, "FIToFIPmtStsRpt") is not None:
        rsn = _first(root, "Rsn")
        return {"message_type": "pacs.002", "schema": kind,
                "end_to_end_id": _text(root, "OrgnlEndToEndId"),
                "status": _text(root, "TxSts"),
                "reason": _text(rsn, "Cd") if rsn is not None else None}
    if _first(root, "FIToFICstmrCdtTrf") is not None:
        amount = _first(root, "IntrBkSttlmAmt")
        minor = None
        if amount is not None and amount.text:
            # Integer minor units (CON-money-is-integer-minor-units); two-decimal
            # currencies only in this reference server.
            minor = int(Decimal(amount.text.strip()) * 100)
        return {"message_type": "pacs.008", "schema": kind,
                "end_to_end_id": _text(root, "EndToEndId"),
                "amount_minor": minor,
                "currency": amount.get("Ccy") if amount is not None else None}
    raise ToolError("not a pacs.002 or pacs.008 message")


@server.tool()
def explain_status(code: str) -> dict:
    """Explain an ISO 20022 external status reason code, such as AC04 or AM05.

    Side effects: none.
    """
    codes = json.loads(CODES.read_text(encoding="utf-8"))
    entry = codes.get(code.strip().upper())
    if entry is None:
        raise ToolError(f"unknown status reason code {code}")
    return {"code": code.strip().upper(), **entry}


if __name__ == "__main__":
    server.run()
