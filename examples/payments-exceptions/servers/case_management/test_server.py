"""The server exposes exactly the operations TOOL-case-management declares (PAC-073)."""
import asyncio

import pytest

pytest.importorskip("mcp")

from servers.case_management.server import server  # noqa: E402

DECLARED = ['add_comment', 'get_case', 'propose_repair', 'release_funds']


def test_tools_match_the_artifact():
    tools = asyncio.run(server.list_tools())
    assert sorted(t.name for t in tools) == DECLARED
