"""``keelspec serve``: governed agents over HTTP, or as MCP tools (spec M12).

Routes::

    GET  /healthz                     bundle sha256 and validate status (no auth)
    POST /v1/agents/{agent_id}/runs   {"input": "..."}                 -> a run
    GET  /v1/runs/{run_id}            the run record (content-free) + pending approvals
    POST /v1/runs/{run_id}/approvals  {"step": N, "by": "name"}         -> the resumed run

The server executes the bundle it loaded at start, and refuses to start on one that
fails validation (I-10); ``/healthz`` reports which bundle that is. Only agents with
``status: deployed`` are served unless ``--any-status`` is given for a demo.

Two tokens, kept apart on purpose (segregation of duties):

- ``KEELSPEC_SERVE_TOKEN`` lets a caller start runs and read records. It is required
  whenever the server listens on anything but loopback.
- ``KEELSPEC_APPROVER_TOKEN`` is the only thing that can approve a paused call. With
  no approver token, approvals over HTTP are off and ``keelspec approvals`` is the
  way to sign. The two tokens must differ: whoever asks an agent to act must not be
  able to approve what it asks for.

A run is executed in the request's thread and the response is the finished (or
paused) run. Standard library only; the MCP mode needs ``keelspec[runtime]``.
"""
from __future__ import annotations

import dataclasses
import hmac
import ipaddress
import json
import re
import sys
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .. import __version__
from . import approvals, records
from .agent import ApprovalPending, resume_agent, run_agent
from .fixtures import ToolError
from .policy import AgentPolicies
from .router_client import RuntimeSettings

MAX_BODY = 64 * 1024
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
AGENT_RUNS = re.compile(r"^/v1/agents/([A-Za-z0-9._-]+)/runs$")
RUN = re.compile(r"^/v1/runs/([^/]+)$")
RUN_APPROVALS = re.compile(r"^/v1/runs/([^/]+)/approvals$")


class ServeRefused(RuntimeError):
    """The server will not start with this configuration."""


def is_loopback(host: str) -> bool:
    if host in ("localhost", ""):
        return host == "localhost"
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclasses.dataclass
class App:
    """Everything a request needs. ``handle`` is pure request -> response, so tests
    drive it without sockets; ``make_server`` puts it behind HTTP."""

    root: Any
    bundle: dict
    provenance: dict
    validation: dict                       # {"ok": bool, "errors": n, "warnings": n}
    settings: RuntimeSettings
    router_factory: Callable[[], Any]
    executor_factory: Callable[[], Any]
    prices: dict = dataclasses.field(default_factory=dict)
    run_token: str | None = None
    approve_token: str | None = None
    any_status: bool = False

    def __post_init__(self):
        if self.approve_token and self.run_token and \
                hmac.compare_digest(self.approve_token, self.run_token):
            raise ServeRefused("KEELSPEC_APPROVER_TOKEN must differ from KEELSPEC_SERVE_TOKEN: "
                               "whoever starts a run must not be able to approve it")

    # ── helpers ──────────────────────────────────────────────────────────────
    def agents(self) -> dict[str, dict]:
        return {a["id"]: a for a in self.bundle.get("agents", []) if a.get("id")}

    def servable(self) -> dict[str, dict]:
        return {i: a for i, a in self.agents().items()
                if self.any_status or a.get("status") == "deployed"}

    @staticmethod
    def _token(headers: dict) -> str:
        value = headers.get("authorization") or ""
        return value[7:].strip() if value.lower().startswith("bearer ") else ""

    @staticmethod
    def _matches(given: str, expected: str | None) -> bool:
        return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())

    def _run_kw(self, executor) -> dict:
        return {"root": self.root, "router": self.router_factory(), "executor": executor,
                "settings": self.settings, "prices": self.prices}

    def _result(self, result) -> dict:
        rec = result.record
        pending = [{"step": r["step"], "tool_id": r["tool_id"], "operation": r["operation"],
                    "approvers": r["approvers"]}
                   for r in (approvals.read(self.root, rec.run_id) or {}).get("requests", [])
                   if r["status"] == "pending"]
        return {"run_id": rec.run_id, "agent_id": rec.agent_id, "outcome": rec.outcome,
                "steps": len(rec.steps), "final_answer": result.final_answer,
                "approvals_pending": pending}

    def _execute(self, fn: Callable[[Any], Any]) -> tuple[int, dict]:
        executor = self.executor_factory()
        try:
            return 200, self._result(fn(executor))
        except ApprovalPending as exc:
            return 409, {"error": str(exc)}
        except ToolError as exc:
            return 503, {"error": str(exc)}
        finally:
            close = getattr(executor, "close", None)
            if close:
                close()

    # ── the routes ───────────────────────────────────────────────────────────
    def run(self, agent_id: str, text: str) -> tuple[int, dict]:
        """Start a run; shared by HTTP and MCP."""
        agent = self.agents().get(agent_id)
        if agent is None:
            return 404, {"error": f"no agent {agent_id}"}
        if agent_id not in self.servable():
            return 409, {"error": f"{agent_id} is {agent.get('status') or 'not deployed'}; "
                                  "only deployed agents are served"}
        def start(ex):
            # Open every tool first: a drifted server refuses the run (PAC-073)
            # before the model is asked anything, as `keelspec run` does.
            if hasattr(ex, "open"):
                for tool in AgentPolicies.from_bundle(self.bundle, agent_id).tools.values():
                    ex.open(tool)
            return run_agent(self.bundle, self.provenance, agent_id, text, **self._run_kw(ex))
        status, body = self._execute(start)
        return (201 if status == 200 else status), body

    def health(self) -> tuple[int, dict]:
        body = {"status": "ok" if self.validation.get("ok") else "failing",
                "version": __version__,
                "bundle_sha256": self.provenance.get("bundle_sha256", ""),
                "validate": {"errors": self.validation.get("errors", 0),
                             "warnings": self.validation.get("warnings", 0)},
                "agents": sorted(self.servable())}
        return (200 if self.validation.get("ok") else 503), body

    def handle(self, method: str, path: str, headers: dict, body: bytes) -> tuple[int, dict]:
        headers = {k.lower(): v for k, v in headers.items()}
        path = path.split("?", 1)[0]
        if path == "/healthz":
            return self.health() if method == "GET" else (405, {"error": "use GET"})

        m_runs, m_run, m_appr = AGENT_RUNS.match(path), RUN.match(path), RUN_APPROVALS.match(path)
        if not (m_runs or m_run or m_appr):
            return 404, {"error": "not found"}
        token = self._token(headers)
        if m_appr:
            if not self.approve_token:
                return 403, {"error": "approvals over HTTP are off (no KEELSPEC_APPROVER_TOKEN); "
                                      "use keelspec approvals approve"}
            if not self._matches(token, self.approve_token):
                return 401, {"error": "approving needs the approver token"}
        elif self.run_token and not self._matches(token, self.run_token):
            return 401, {"error": "missing or wrong bearer token"}

        if m_run:
            if method != "GET":
                return 405, {"error": "use GET"}
            run_id = m_run.group(1)
            if not RUN_ID.match(run_id):
                return 400, {"error": "bad run id"}
            try:
                rec = records.read(self.root, run_id)
            except (OSError, ValueError):
                return 404, {"error": f"no run {run_id}"}
            pending = [r for r in (approvals.read(self.root, run_id) or {}).get("requests", [])
                       if r["status"] == "pending"]
            return 200, {"record": rec.to_dict(),
                         "approvals_pending": [{k: r[k] for k in
                                                ("step", "tool_id", "operation", "approvers")}
                                               for r in pending]}

        if method != "POST":
            return 405, {"error": "use POST"}
        if len(body) > MAX_BODY:
            return 413, {"error": f"body larger than {MAX_BODY} bytes"}
        try:
            data = json.loads(body or b"{}")
            if not isinstance(data, dict):
                raise ValueError("expected a JSON object")
        except ValueError as exc:
            return 400, {"error": f"bad JSON: {exc}"}

        if m_runs:
            text = data.get("input")
            if not isinstance(text, str) or not text.strip():
                return 400, {"error": "input must be a non-empty string"}
            return self.run(m_runs.group(1), text)

        run_id = m_appr.group(1)
        step, by = data.get("step"), data.get("by")
        if not RUN_ID.match(run_id):
            return 400, {"error": "bad run id"}
        if not isinstance(step, int) or isinstance(step, bool) or not isinstance(by, str) \
                or not by.strip():
            return 400, {"error": "give step (an integer) and by (who approves)"}
        try:
            approvals.approve(self.root, run_id, step, by.strip())
        except (KeyError, ValueError) as exc:
            return 404, {"error": str(exc).strip("'\"")}
        try:
            return self._execute(lambda ex: resume_agent(
                self.bundle, self.provenance, run_id, **self._run_kw(ex)))
        except KeyError as exc:
            return 409, {"error": str(exc).strip("'\"")}


def make_server(app: App, host: str = "127.0.0.1", port: int = 8080) -> ThreadingHTTPServer:
    """The HTTP server. Refuses to listen beyond loopback without a run token."""
    if not is_loopback(host) and not app.run_token:
        raise ServeRefused(f"listening on {host} needs KEELSPEC_SERVE_TOKEN; without it "
                           "anyone who can reach the port could run your agents")

    class Handler(BaseHTTPRequestHandler):
        server_version = f"keelspec/{__version__}"
        sys_version = ""

        def _respond(self) -> None:
            length = int(self.headers.get("content-length") or 0)
            if length > MAX_BODY:
                status, body = 413, {"error": f"body larger than {MAX_BODY} bytes"}
            else:
                raw = self.rfile.read(length) if length else b""
                try:
                    status, body = app.handle(self.command, self.path, dict(self.headers), raw)
                except Exception as exc:          # never leak a traceback to a caller
                    print(f"keelspec serve: {type(exc).__name__}: {exc}", file=sys.stderr)
                    status, body = 500, {"error": "internal error"}
            payload = json.dumps(body).encode()
            self.send_response(status, HTTPStatus(status).phrase)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = do_PUT = do_DELETE = _respond

        def log_message(self, fmt: str, *args: Any) -> None:
            # Method, path and status only: never bodies.
            print(f"keelspec serve: {self.command} {self.path.split('?', 1)[0]} "
                  f"{args[1] if len(args) > 1 else ''}", file=sys.stderr)

    return ThreadingHTTPServer((host, port), Handler)


def build_mcp_server(app: App):
    """Each servable agent as one MCP tool (``keelspec serve --mcp``). A paused run
    comes back as ``awaiting_approval``; approving is not something the caller of an
    agent can do from here."""
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError:                                   # mcp 1.x
        from mcp.server.fastmcp import FastMCP as MCPServer
    server = MCPServer("keelspec-agents")

    def tool_for(agent_id: str) -> Callable[[str], dict]:
        # A closure, not a default argument: a default would show up in the tool's
        # input schema as something the caller could set.
        def call(input: str) -> dict:
            status, body = app.run(agent_id, input)
            if status not in (200, 201):
                raise RuntimeError(body.get("error", f"status {status}"))
            return body
        return call

    for agent_id, agent in sorted(app.servable().items()):
        call = tool_for(agent_id)
        description = (agent.get("purpose") or agent.get("title") or agent_id).strip()
        server.add_tool(call, name=agent_id, description=f"{description} "
                        "(a governed agent: policies decide every tool call; repairs and "
                        "other gated actions pause for a person)")
    return server
