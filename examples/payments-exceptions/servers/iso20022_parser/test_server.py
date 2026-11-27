"""The server exposes exactly the operations TOOL-iso20022-parser declares (PAC-073)."""
import asyncio

import pytest

pytest.importorskip("mcp")

from servers.iso20022_parser.server import server  # noqa: E402

DECLARED = ['explain_status', 'parse_message']


def test_tools_match_the_artifact():
    tools = asyncio.run(server.list_tools())
    assert sorted(t.name for t in tools) == DECLARED
