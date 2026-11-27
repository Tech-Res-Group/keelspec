"""v2 M12: ``keelspec serve`` -- the HTTP API, its tokens, and the MCP mode.

End to end through a real socket with a mocked router and fixture tools.
"""
from __future__ import annotations

import json
import shutil
import threading

import httpx
import pytest
from test_runtime import AGENT, EXAMPLE, FakeRouter, call

from keelspec.cli import main
from keelspec.config import load_config
from keelspec.runtime import serve as serve_mod
from keelspec.runtime.bundle import load_bundle
from keelspec.runtime.fixtures import FixtureExecutor, ToolError
from keelspec.runtime.router_client import RouterClient, RouterSettings, RuntimeSettings
from keelspec.runtime.serve import App, ServeRefused, build_mcp_server, is_loopback, make_server

SCN = "SCN-ac04-closed-account"
RUN_TOKEN, APPROVE_TOKEN = "run-token-1", "approve-token-2"


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "ex"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def _app(root, fake, **kw) -> App:
    bundle, prov = load_bundle(load_config(root / "product.config.yaml"), root)
    defaults = {"any_status": True, "run_token": None, "approve_token": None}
    defaults.update(kw)
    return App(root=root, bundle=bundle, provenance=prov,
               validation={"ok": True, "errors": 0, "warnings": 0},
               settings=RuntimeSettings(),
               router_factory=lambda: RouterClient(
                   RouterSettings(base_url="https://router.test/v1"), api_key="k",
                   transport=httpx.MockTransport(fake), sleep=lambda s: None),
               executor_factory=lambda: FixtureExecutor.from_scenario(bundle, SCN), **defaults)


def _post(app, path, body, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return app.handle("POST", path, headers, json.dumps(body).encode())


# ── routes, without sockets ──────────────────────────────────────────────────
def test_health(project):
    app = _app(project, FakeRouter())
    status, body = app.handle("GET", "/healthz", {}, b"")
    assert status == 200 and body["status"] == "ok"
    assert len(body["bundle_sha256"]) == 64 and body["agents"] == [AGENT]
    app.validation = {"ok": False, "errors": 2, "warnings": 0}
    status, body = app.handle("GET", "/healthz?x=1", {}, b"")
    assert status == 503 and body["status"] == "failing" and body["validate"]["errors"] == 2
    assert app.handle("POST", "/healthz", {}, b"")[0] == 405


def test_run_and_read_it_back(project):
    app = _app(project, FakeRouter({"content": "AC04: the account is closed."}))
    status, body = _post(app, f"/v1/agents/{AGENT}/runs", {"input": "Case 88121"})
    assert status == 201 and body["outcome"] == "completed"
    assert body["final_answer"] == "AC04: the account is closed."
    status, got = app.handle("GET", f"/v1/runs/{body['run_id']}", {}, b"")
    assert status == 200 and got["record"]["outcome"] == "completed"
    assert "AC04" not in json.dumps(got["record"])           # the record is content-free
    assert got["approvals_pending"] == []


@pytest.mark.parametrize("method,path,body,expected", [
    ("POST", f"/v1/agents/{AGENT}/runs", b"not json", 400),
    ("POST", f"/v1/agents/{AGENT}/runs", b"[1]", 400),
    ("POST", f"/v1/agents/{AGENT}/runs", b'{"input": "  "}', 400),
    ("GET", f"/v1/agents/{AGENT}/runs", b"", 405),
    ("POST", "/v1/agents/AGENT-nope/runs", b'{"input": "x"}', 404),
    ("POST", "/v1/runs/r1", b"", 405),
    ("GET", "/v1/runs/no-such-run", b"", 404),
    ("GET", "/v1/runs/..%2Fetc", b"", 400),
    ("GET", "/nope", b"", 404),
])
def test_bad_requests(project, method, path, body, expected):
    app = _app(project, FakeRouter())
    assert app.handle(method, path, {}, body)[0] == expected


def test_oversized_body(project):
    # Not a parametrize case: the body would become the test id, which pytest puts
    # in an environment variable that Windows caps at 32767 characters.
    app = _app(project, FakeRouter())
    assert app.handle("POST", f"/v1/agents/{AGENT}/runs", {}, b"x" * (65 * 1024))[0] == 413


def test_only_deployed_agents_are_served(project):
    app = _app(project, FakeRouter(), any_status=False)
    status, body = _post(app, f"/v1/agents/{AGENT}/runs", {"input": "x"})
    assert status == 409 and "building" in body["error"]
    assert app.servable() == {}


def test_run_token(project):
    app = _app(project, FakeRouter(), run_token=RUN_TOKEN)
    path = f"/v1/agents/{AGENT}/runs"
    assert _post(app, path, {"input": "x"})[0] == 401
    assert _post(app, path, {"input": "x"}, token="wrong")[0] == 401
    assert _post(app, path, {"input": "x"}, token=RUN_TOKEN)[0] == 201
    assert app.handle("GET", "/healthz", {}, b"")[0] == 200     # health needs no token


def test_tokens_must_differ(project):
    with pytest.raises(ServeRefused, match="must differ"):
        _app(project, FakeRouter(), run_token="same", approve_token="same")


def test_approval_pause_and_resume_over_http(project):
    fake = FakeRouter(call("TOOL-case-management", "propose_repair", {"amount_minor": 125000}),
                      {"content": "Repair proposed."})
    app = _app(project, fake, run_token=RUN_TOKEN, approve_token=APPROVE_TOKEN)
    status, body = _post(app, f"/v1/agents/{AGENT}/runs", {"input": "Case 88121"}, RUN_TOKEN)
    assert status == 201 and body["outcome"] == "awaiting_approval"
    (pending,) = body["approvals_pending"]
    assert pending["operation"] == "propose_repair" and pending["approvers"] == ["payments-ops-lead"]
    run_id, step = body["run_id"], pending["step"]
    got = app.handle("GET", f"/v1/runs/{run_id}", {"Authorization": f"Bearer {RUN_TOKEN}"}, b"")
    assert got[1]["approvals_pending"][0]["step"] == step

    path = f"/v1/runs/{run_id}/approvals"
    # The caller who started the run cannot approve it.
    assert _post(app, path, {"step": step, "by": "Colin"}, RUN_TOKEN)[0] == 401
    assert _post(app, path, {"step": "1", "by": "Colin"}, APPROVE_TOKEN)[0] == 400
    assert _post(app, path, {"step": step, "by": " "}, APPROVE_TOKEN)[0] == 400
    assert _post(app, "/v1/runs/..bad/approvals", {"step": 1, "by": "x"}, APPROVE_TOKEN)[0] == 400
    assert _post(app, path, {"step": 99, "by": "Colin"}, APPROVE_TOKEN)[0] == 404
    status, done = _post(app, path, {"step": step, "by": "Colin"}, APPROVE_TOKEN)
    assert status == 200 and done["outcome"] == "completed"
    assert done["final_answer"] == "Repair proposed."
    status, _again = _post(app, path, {"step": step, "by": "Colin"}, APPROVE_TOKEN)
    assert status in (404, 409)


def test_approvals_are_off_without_an_approver_token(project):
    app = _app(project, FakeRouter())
    status, body = _post(app, "/v1/runs/r1/approvals", {"step": 1, "by": "x"})
    assert status == 403 and "keelspec approvals approve" in body["error"]


def test_drifted_server_refuses_the_run(project):
    class Drifted:
        closed = False

        def open(self, tool):
            raise ToolError(f"PAC-073 {tool['id']}: drifted")

        def call(self, tool, op, args):
            raise AssertionError("never called")

        def close(self):
            Drifted.closed = True
    app = _app(project, FakeRouter())
    app.executor_factory = Drifted
    status, body = _post(app, f"/v1/agents/{AGENT}/runs", {"input": "x"})
    assert status == 503 and "PAC-073" in body["error"] and Drifted.closed


def test_resume_of_a_run_that_is_not_paused(project, monkeypatch):
    app = _app(project, FakeRouter(), approve_token=APPROVE_TOKEN)
    monkeypatch.setattr(serve_mod.approvals, "approve", lambda *a: {})
    status, body = _post(app, "/v1/runs/r-not-paused/approvals", {"step": 1, "by": "x"},
                         APPROVE_TOKEN)
    assert status == 409 and "not paused" in body["error"]


def test_loopback_rule():
    assert is_loopback("127.0.0.1") and is_loopback("::1") and is_loopback("localhost")
    assert not is_loopback("0.0.0.0") and not is_loopback("") and not is_loopback("example.org")


def test_listening_beyond_loopback_needs_a_token(project):
    with pytest.raises(ServeRefused, match="KEELSPEC_SERVE_TOKEN"):
        make_server(_app(project, FakeRouter()), "0.0.0.0", 0)


# ── end to end, through a socket ─────────────────────────────────────────────
@pytest.fixture()
def live(project):
    fake = FakeRouter(call("TOOL-case-management", "propose_repair", {"amount_minor": 125000}),
                      {"content": "Repair proposed."})
    app = _app(project, fake, run_token=RUN_TOKEN, approve_token=APPROVE_TOKEN)
    server = make_server(app, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    yield app, f"http://{host}:{port}"
    server.shutdown()
    server.server_close()


def test_end_to_end_over_http(live):
    _, base = live
    run_h = {"Authorization": f"Bearer {RUN_TOKEN}"}
    with httpx.Client(base_url=base, timeout=30) as http:
        health = http.get("/healthz")
        assert health.status_code == 200 and health.headers["content-type"] == "application/json"
        r = http.post(f"/v1/agents/{AGENT}/runs", json={"input": "Case 88121"}, headers=run_h)
        assert r.status_code == 201 and r.json()["outcome"] == "awaiting_approval"
        run_id, step = r.json()["run_id"], r.json()["approvals_pending"][0]["step"]
        assert http.get(f"/v1/runs/{run_id}", headers=run_h).json()["record"]["run_id"] == run_id
        done = http.post(f"/v1/runs/{run_id}/approvals", json={"step": step, "by": "Colin"},
                         headers={"Authorization": f"Bearer {APPROVE_TOKEN}"})
        assert done.status_code == 200 and done.json()["outcome"] == "completed"
        big = http.post(f"/v1/agents/{AGENT}/runs", content=b"x" * (70 * 1024), headers=run_h)
        assert big.status_code == 413
        assert http.delete("/v1/runs/x", headers=run_h).status_code == 405


def test_an_internal_error_does_not_leak(live, monkeypatch, capsys):
    app, base = live

    def boom(*a):
        raise RuntimeError("secret detail")
    monkeypatch.setattr(app, "handle", boom)
    r = httpx.get(f"{base}/healthz", timeout=30)
    assert r.status_code == 500 and r.json() == {"error": "internal error"}
    assert "secret detail" not in r.text


# ── MCP mode ─────────────────────────────────────────────────────────────────
def test_agents_as_mcp_tools(project):
    pytest.importorskip("mcp")
    import anyio
    from mcp import Client
    app = _app(project, FakeRouter({"content": "AC04: closed."}))
    server = build_mcp_server(app)

    async def go():
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            result = await client.call_tool(AGENT, {"input": "Case 88121"})
            return tools, result
    tools, result = anyio.run(go)
    assert [t.name for t in tools] == [AGENT]
    assert list(tools[0].input_schema["properties"]) == ["input"]   # nothing else settable
    assert "governed agent" in tools[0].description
    from keelspec.runtime.mcp_client import result_data
    data = result_data(result)
    assert data["outcome"] == "completed" and data["final_answer"] == "AC04: closed."

    app.any_status = False                     # the tool exists, but the agent is not deployed
    app.bundle["agents"][0]["status"] = "deployed"
    server = build_mcp_server(app)
    app.bundle["agents"][0]["status"] = "building"

    async def refused():
        async with Client(server) as client:
            return await client.call_tool(AGENT, {"input": "x"})
    assert anyio.run(refused).is_error


# ── the CLI ──────────────────────────────────────────────────────────────────
def test_cli_serve(project, monkeypatch, capsys):
    root = str(project)
    assert main(["-C", root, "serve"]) == 1                          # nothing is deployed
    assert "nothing to serve" in capsys.readouterr().err
    assert main(["-C", root, "serve", "--any-status", "--fixtures", "SCN-nope"]) == 2
    monkeypatch.delenv("KEELSPEC_SERVE_TOKEN", raising=False)
    assert main(["-C", root, "serve", "--any-status", "--fixtures", SCN,
                 "--host", "0.0.0.0"]) == 2
    assert "KEELSPEC_SERVE_TOKEN" in capsys.readouterr().err

    class FakeServer:
        server_address = ("127.0.0.1", 9999)
        closed = False

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            FakeServer.closed = True
    monkeypatch.setattr(serve_mod, "make_server", lambda app, host, port: FakeServer())
    assert main(["-C", root, "serve", "--any-status", "--fixtures", SCN]) == 0
    err = capsys.readouterr().err
    assert f"serving {AGENT} on http://127.0.0.1:9999" in err and FakeServer.closed
    assert "approvals over HTTP are off" in err
    monkeypatch.setattr(serve_mod, "build_mcp_server",
                        lambda app: type("S", (), {"run": lambda self: None})())
    assert main(["-C", root, "serve", "--any-status", "--mcp"]) == 0


def test_cli_serve_refuses_a_failing_bundle(project, capsys):
    (project / "product" / "policies" / "POL-no-funds-movement.md").unlink()
    assert main(["-C", str(project), "serve", "--any-status", "--fixtures", SCN]) == 1
    assert "PAC-079" in capsys.readouterr().err
