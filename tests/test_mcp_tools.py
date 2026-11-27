"""v2 M8: the MCP client, ``keelspec tools check`` / ``scaffold``, and the three
reference servers of the example.

In-process servers for most tests; a few spawn the example's real stdio servers,
which is what ``keelspec tools check`` and ``keelspec run`` do.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys

import pytest

pytest.importorskip("mcp")

import anyio
import httpx
import mcp_types
from mcp.server.mcpserver import MCPServer
from test_runtime import AGENT, EXAMPLE, FakeRouter, call

from keelspec.cli import main
from keelspec.config import load_config
from keelspec.runtime import records
from keelspec.runtime.agent import run_agent
from keelspec.runtime.bundle import load_bundle
from keelspec.runtime.fixtures import ToolError
from keelspec.runtime.mcp_client import (
    MCPExecutor,
    ToolDrift,
    drift,
    result_data,
    server_target,
)
from keelspec.runtime.router_client import (
    RouterClient,
    RouterSettings,
    RuntimeSettings,
)
from keelspec.runtime.scaffold import render_server, scaffold, slug

PARSER = {"id": "TOOL-iso20022-parser", "timeout_seconds": 5,
          "operations": [{"name": "parse_message"}, {"name": "explain_status"}]}
CASES = {"id": "TOOL-case-management", "timeout_seconds": 5,
         "operations": [{"name": n} for n in
                        ("get_case", "add_comment", "propose_repair", "release_funds")]}
LEDGER = {"id": "TOOL-payments-ledger", "timeout_seconds": 5,
          "operations": [{"name": "get_payment"}, {"name": "list_postings"}]}


@pytest.fixture()
def servers(monkeypatch):
    """The example's reference servers, imported in-process."""
    monkeypatch.syspath_prepend(str(EXAMPLE))
    from servers.case_management.server import server as cases
    from servers.iso20022_parser.server import server as parser
    from servers.payments_ledger.server import server as ledger
    return {"TOOL-case-management": cases, "TOOL-iso20022-parser": parser,
            "TOOL-payments-ledger": ledger}


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "ex"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def _ks(root, *argv) -> int:
    return main(["-C", str(root), *argv])


# ── pure pieces ──────────────────────────────────────────────────────────────
def test_drift_reports_both_directions():
    assert drift(PARSER, ["parse_message", "explain_status"]) == []
    problems = drift(PARSER, ["parse_message", "release_funds"])
    assert problems == [
        "the server exposes 'release_funds', which TOOL-iso20022-parser does not declare",
        "TOOL-iso20022-parser declares 'explain_status', which the server does not expose"]


def test_result_data_shapes():
    text = mcp_types.TextContent(type="text", text='{"a": 1}')
    assert result_data(mcp_types.CallToolResult(content=[text])) == {"a": 1}
    plain = mcp_types.TextContent(type="text", text="hello")
    assert result_data(mcp_types.CallToolResult(content=[plain])) == "hello"
    assert result_data(mcp_types.CallToolResult(content=[], structured_content={"x": 2})) == {"x": 2}
    assert result_data(mcp_types.CallToolResult(content=[],
                                                structured_content={"result": [1]})) == [1]
    with pytest.raises(ToolError, match="boom"):
        result_data(mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="boom")], is_error=True))


def test_server_target_stdio_and_errors(tmp_path):
    tool = {"id": "TOOL-x", "transport": "stdio",
            "server": {"command": "python", "args": ["-m", "servers.x"], "env": {"A": "1"}}}
    params = server_target(tool, tmp_path)
    assert params.command == sys.executable          # the interpreter running KeelSpec
    assert params.args == ["-m", "servers.x"] and params.env == {"A": "1"}
    assert pathlib.Path(params.cwd) == tmp_path
    with pytest.raises(ToolError, match=r"no server.command"):
        server_target({"id": "TOOL-x", "transport": "stdio", "server": {}}, tmp_path)
    with pytest.raises(ToolError, match=r"no server.url"):
        server_target({"id": "TOOL-x", "transport": "http", "server": {}}, tmp_path)
    with pytest.raises(ToolError, match="unknown transport"):
        server_target({"id": "TOOL-x", "transport": "carrier-pigeon"}, tmp_path)


def test_http_target_carries_traceparent(monkeypatch, tmp_path):
    import mcp.client.streamable_http as sh
    seen = {}

    def fake(url, http_client=None, **kw):
        seen["url"], seen["headers"] = url, dict(http_client.headers)
        return "transport"
    monkeypatch.setattr(sh, "streamable_http_client", fake)
    tool = {"id": "TOOL-x", "transport": "http",
            "server": {"url": "https://tools.test/mcp", "headers": {"x-team": "ops"}}}
    tp = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    assert server_target(tool, tmp_path, traceparent=tp) == "transport"
    assert seen["url"] == "https://tools.test/mcp"
    assert seen["headers"]["traceparent"] == tp and seen["headers"]["x-team"] == "ops"


# ── the executor, in-process ─────────────────────────────────────────────────
def test_executor_calls_the_reference_servers(servers):
    case = json.loads((EXAMPLE / "fixtures" / "cases.json").read_text())["88121"]
    with MCPExecutor(connect=lambda t: servers[t["id"]]) as ex:
        assert ex.call(CASES, "get_case", {"case_id": "88121"})["reason"] == "AC04"
        parsed = ex.call(PARSER, "parse_message", {"xml": case["message"]})
        assert parsed == {"message_type": "pacs.002", "schema": "pacs.002.001.10",
                          "end_to_end_id": "E2E-77F", "status": "RJCT", "reason": "AC04"}
        assert ex.call(PARSER, "explain_status", {"code": "am05"})["name"] == "Duplication"
        assert ex.call(LEDGER, "list_postings", {"end_to_end_id": "E2E-91C"})["postings"][0]["settled"]
        assert "postings" not in ex.call(LEDGER, "get_payment", {"end_to_end_id": "E2E-77F"})
        comment = ex.call(CASES, "add_comment", {"case_id": "88121", "text": "AC04: closed"})
        assert comment["comment_id"].startswith("CMT-")
        repair = ex.call(CASES, "propose_repair", {"case_id": "88121", "field": "creditor.account",
                                                    "new_value": "EE0000", "amount_minor": 125000})
        assert repair["status"] == "proposed"
        # The server would release funds: the guarantee is the policy, not the tool.
        assert ex.call(CASES, "release_funds", {"case_id": "88121", "amount_minor": 1})["released_minor"] == 1
        with pytest.raises(ToolError, match="unknown status reason code ZZ99"):
            ex.call(PARSER, "explain_status", {"code": "ZZ99"})
        with pytest.raises(ToolError, match="no case 1"):
            ex.call(CASES, "get_case", {"case_id": "1"})
        with pytest.raises(ToolError, match="no payment"):
            ex.call(LEDGER, "get_payment", {"end_to_end_id": "nope"})
        assert ex.calls[0] == ("TOOL-case-management", "get_case")


def test_parser_handles_pacs008_and_refuses_dtds(servers):
    pacs008 = ('<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">'
               '<FIToFICstmrCdtTrf><CdtTrfTxInf><PmtId><EndToEndId>E2E-1</EndToEndId></PmtId>'
               '<IntrBkSttlmAmt Ccy="EUR">1250.00</IntrBkSttlmAmt></CdtTrfTxInf>'
               '</FIToFICstmrCdtTrf></Document>')
    with MCPExecutor(connect=lambda t: servers[t["id"]]) as ex:
        out = ex.call(PARSER, "parse_message", {"xml": pacs008})
        assert out["amount_minor"] == 125000 and out["currency"] == "EUR"
        assert out["end_to_end_id"] == "E2E-1"
        with pytest.raises(ToolError, match="DTDs"):
            ex.call(PARSER, "parse_message", {"xml": '<!DOCTYPE x [<!ENTITY a "b">]><x/>'})
        with pytest.raises(ToolError, match="not a pacs"):
            ex.call(PARSER, "parse_message", {"xml": "<x/>"})
        with pytest.raises(ToolError, match="too large"):
            ex.call(PARSER, "parse_message", {"xml": "<x>" + "a" * 300_000 + "</x>"})


def test_executor_refuses_a_drifted_server(servers):
    narrow = {**PARSER, "operations": [{"name": "parse_message"}]}
    with MCPExecutor(connect=lambda t: servers[t["id"]]) as ex:
        with pytest.raises(ToolDrift) as info:
            ex.open(narrow)
        assert str(info.value).startswith("PAC-073 TOOL-iso20022-parser:")
        assert "exposes 'explain_status'" in str(info.value)
        # tool_names lists without judging: tools check reports drift as diagnostics.
        assert ex.tool_names(narrow) == ["explain_status", "parse_message"]


def test_unreachable_server_is_a_tool_error(tmp_path):
    bad = {"id": "TOOL-x", "transport": "stdio", "operations": [{"name": "a"}],
           "server": {"command": str(tmp_path / "no-such-binary")}}
    with MCPExecutor(tmp_path, open_timeout=10) as ex:
        with pytest.raises(ToolError, match="cannot reach the server"):
            ex.call(bad, "a", {})
        with pytest.raises(ToolError, match="cannot reach the server"):
            ex.tool_names(bad)


def _slow_server() -> MCPServer:
    slow = MCPServer("TOOL-slow")

    @slow.tool()
    async def wait(seconds: float) -> dict:
        await anyio.sleep(seconds)
        return {"waited": seconds}

    @slow.tool()
    def big() -> dict:
        return {"blob": "x" * 5000}
    return slow


def test_timeout_is_enforced():
    tool = {"id": "TOOL-slow", "timeout_seconds": 0.2,
            "operations": [{"name": "wait"}, {"name": "big"}]}
    server = _slow_server()
    with MCPExecutor(connect=lambda t: server) as ex:
        assert ex.call(tool, "wait", {"seconds": 0}) == {"waited": 0}
        with pytest.raises(TimeoutError):
            ex.call(tool, "wait", {"seconds": 5})


def test_open_timeout_is_enforced():
    class Hangs:
        async def __aenter__(self):
            await anyio.sleep(10)

        async def __aexit__(self, *exc):
            return False
    tool = {"id": "TOOL-hang", "operations": [{"name": "a"}]}
    with MCPExecutor(connect=lambda t: Hangs(), open_timeout=0.2) as ex,             pytest.raises(ToolError, match="did not start within"):
        ex.call(tool, "a", {})


# ── limits through the agent loop ────────────────────────────────────────────
def _bundle(root):
    return load_bundle(load_config(root / "product.config.yaml"), root)


def _router(fake):
    return RouterClient(RouterSettings(base_url="https://router.test/v1"), api_key="k",
                        transport=httpx.MockTransport(fake), sleep=lambda s: None)


def test_result_size_and_timeout_limits_in_a_run(project, servers):
    bundle, prov = _bundle(project)
    for tool in bundle["tools"]:
        if tool["id"] == "TOOL-case-management":
            tool["max_result_bytes"] = 120            # get_case is far bigger than this
        if tool["id"] == "TOOL-iso20022-parser":
            tool["timeout_seconds"] = 0.2
    slow_parser = MCPServer("TOOL-iso20022-parser")   # same tools, but explain_status hangs

    @slow_parser.tool()
    def parse_message(xml: str) -> dict:
        return {}

    @slow_parser.tool()
    async def explain_status(code: str) -> dict:
        await anyio.sleep(5)
        return {}
    targets = {**servers, "TOOL-iso20022-parser": slow_parser}
    fake = FakeRouter(call("TOOL-case-management", "get_case", {"case_id": "88121"}),
                      call("TOOL-iso20022-parser", "explain_status", {"code": "AC04"}, "c2"),
                      {"content": "done"})
    with MCPExecutor(connect=lambda t: targets[t["id"]]) as ex:
        result = run_agent(bundle, prov, AGENT, "Case 88121", root=project, router=_router(fake),
                           executor=ex, settings=RuntimeSettings())
    tools = [s for s in result.record.steps if s.kind == "tool"]
    assert [s.outcome for s in tools] == ["truncated", "timeout"]
    sent = fake.bodies()[1]["messages"][-1]["content"]
    assert json.loads(sent)["truncated"] is True and len(sent) < 400


def test_mcp_run_redacts_pii_from_real_server(project, servers):
    bundle, prov = _bundle(project)
    fake = FakeRouter(call("TOOL-payments-ledger", "get_payment", {"end_to_end_id": "E2E-77F"}),
                      {"content": "done"})
    with MCPExecutor(connect=lambda t: servers[t["id"]]) as ex:
        run_agent(bundle, prov, AGENT, "Case 88121", root=project, router=_router(fake),
                  executor=ex, settings=RuntimeSettings())
    sent = fake.bodies()[1]["messages"][-1]["content"]
    assert "Halden" not in sent and "DE8937" not in sent and "125000" in sent


# ── the CLI, against the example's real stdio servers ────────────────────────
def test_tools_check_passes_on_the_example(project, capsys):
    assert _ks(project, "tools", "check") == 0
    assert "3 server(s) checked, 0 PAC-073" in capsys.readouterr().err


def test_tools_check_raises_pac073_when_a_server_drifts(project, capsys):
    path = project / "product" / "tools" / "TOOL-iso20022-parser.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("  - name: explain_status", "  - name: explain_code"),
                    encoding="utf-8")
    assert _ks(project, "tools", "check", "TOOL-iso20022-parser") == 1
    out = capsys.readouterr().out
    assert "PAC-073 product/tools/TOOL-iso20022-parser.md:" in out
    assert "exposes 'explain_status'" in out and "declares 'explain_code'" in out
    assert _ks(project, "tools", "check", "TOOL-iso20022-parser", "--json") == 1
    data = json.loads(capsys.readouterr().out)
    assert {f["code"] for f in data["findings"]} == {"PAC-073"}


def test_tools_cli_argument_errors(project, tmp_path, capsys):
    assert _ks(project, "tools", "check", "TOOL-nope") == 2
    assert _ks(project, "tools", "scaffold") == 2
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "product.config.yaml").write_text("product_dir: product\ntypes: []\n")
    assert _ks(bare, "tools", "check") == 2
    path = project / "product" / "tools" / "TOOL-payments-ledger.md"
    path.write_text(path.read_text(encoding="utf-8").replace(
        '["-m", "servers.payments_ledger"]', '["-m", "servers.not_there"]'), encoding="utf-8")
    assert _ks(project, "tools", "check", "TOOL-payments-ledger") == 1
    assert "cannot check:" in capsys.readouterr().out


def test_run_uses_real_servers_and_refuses_drift(project, monkeypatch, capsys):
    import keelspec.runtime.router_client as rc
    fake = FakeRouter(call("TOOL-case-management", "get_case", {"case_id": "88121"}),
                      call("TOOL-iso20022-parser", "explain_status", {"code": "AC04"}, "c2"),
                      {"content": "AC04: the creditor account is closed."})
    real = rc.RouterClient
    monkeypatch.setattr(rc, "RouterClient", lambda settings=None, **kw: real(
        settings, transport=httpx.MockTransport(fake), sleep=lambda s: None, **kw))
    assert _ks(project, "run", AGENT, "Case 88121: pacs.002 RJCT AC04 on E2E-77F") == 0
    out = capsys.readouterr()
    assert "closed" in out.out
    run_id = out.err.split("── run ")[1].split(":")[0]
    rec = records.read(project, run_id)
    assert [s.outcome for s in rec.steps if s.kind == "tool"] == ["ok", "ok"]
    fed = fake.bodies()[2]["messages"][-1]["content"]
    assert "Account number specified has been closed" in fed

    # A server that drifts from its artifact (here: it grew a tool nobody declared)
    # refuses the run before the model is asked anything.
    path = project / "servers" / "iso20022_parser" / "server.py"
    path.write_text(path.read_text(encoding="utf-8").replace(
        'if __name__ == "__main__":',
        '@server.tool()\ndef rewrite_message(xml: str) -> dict:\n    return {}\n\n\n'
        'if __name__ == "__main__":'), encoding="utf-8")
    calls_before = len(fake.requests)
    assert _ks(project, "run", AGENT, "Case 88121") == 1
    err = capsys.readouterr().err
    assert "PAC-073 TOOL-iso20022-parser" in err and "rewrite_message" in err
    assert len(fake.requests) == calls_before


# ── scaffolding ──────────────────────────────────────────────────────────────
def test_slug_names():
    assert slug("TOOL-payments-ledger") == "payments_ledger"
    assert slug("TOOL-3d-printer") == "tool_3d_printer"
    assert slug("TOOL-class") == "tool_class"


def test_render_server_types_and_escapes():
    tool = {"id": "TOOL-t", "title": 'Has """ quotes', "operations": [
        {"name": "op", "side_effects": "read", "description": 'say """hi"""',
         "input_schema": {"type": "object", "required": ["a"],
                          "properties": {"b": {"type": "integer"}, "a": {"type": "string"},
                                         "class": {"type": "string"}, "c": {}}}}]}
    src = render_server(tool)
    assert "def op(a: str, b: int | None = None, c: object | None = None) -> dict:" in src
    assert 'say \\"\\"\\"hi\\"\\"\\"' in src
    compile(src, "server.py", "exec")


def test_scaffold_passes_its_generated_test(project, capsys):
    shutil.rmtree(project / "servers")
    assert _ks(project, "tools", "scaffold", "TOOL-case-management") == 0
    written = capsys.readouterr().out
    assert "servers" in written and "test_server.py" in written
    assert _ks(project, "tools", "scaffold", "TOOL-case-management") == 1   # no silent overwrite
    assert "--force" in capsys.readouterr().err
    assert _ks(project, "tools", "scaffold", "TOOL-case-management", "--force") == 0
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "servers"], cwd=project, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "1 passed" in proc.stdout


def test_scaffold_function_refuses_overwrite(tmp_path):
    tool = {"id": "TOOL-t", "operations": [{"name": "a"}]}
    files = scaffold(tool, tmp_path)
    assert (tmp_path / "servers" / "__init__.py") in files
    with pytest.raises(FileExistsError):
        scaffold(tool, tmp_path)
