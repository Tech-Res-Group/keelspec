"""The server exposes exactly the operations TOOL-payments-ledger declares (PAC-073)."""
import asyncio

import pytest

pytest.importorskip("mcp")

from servers.payments_ledger.server import server  # noqa: E402

DECLARED = ['get_payment', 'list_postings']


def test_tools_match_the_artifact():
    tools = asyncio.run(server.list_tools())
    assert sorted(t.name for t in tools) == DECLARED
