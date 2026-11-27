"""The MCP client (spec 6.2): how an allowed call reaches a real tool server.

One session per TOOL- artifact, opened on first use and closed when the run ends.
``stdio`` launches ``server.command`` as a subprocess from the project root;
``http`` speaks streamable HTTP to ``server.url`` and forwards the run's W3C
``traceparent`` so server-side logs join the run's trace.

On open the client lists the server's tools and compares them with the artifact's
``operations``. Any difference, in either direction, refuses the session with
PAC-073: the spec, not the server, says what the agent may do. ``keelspec tools
check`` runs the same comparison without running an agent.

Every call is bounded by the artifact's ``timeout_seconds`` (a ``TimeoutError``,
which the agent loop records as a ``timeout`` step). ``max_result_bytes`` is
enforced by the agent loop for every executor, so fixtures and MCP behave alike.

The SDK (``mcp>=2``, from ``keelspec[runtime]``) is imported lazily: nothing here
loads it until a session opens.
"""
from __future__ import annotations

import concurrent.futures
import contextlib
import json
import math
import pathlib
import sys
from collections.abc import Callable, Iterable
from typing import Any

from ..agents import operations
from .fixtures import ToolError

DEFAULT_TIMEOUT_SECONDS = 30.0
OPEN_TIMEOUT_SECONDS = 30.0


class ToolDrift(ToolError):
    """PAC-073: the server's tool list and the artifact's operations differ."""

    def __init__(self, tool_id: str, problems: list[str]):
        self.tool_id, self.problems = tool_id, problems
        super().__init__(f"PAC-073 {tool_id}: " + "; ".join(problems))


def drift(tool: dict, served: Iterable[str]) -> list[str]:
    """What differs between a tool artifact's operations and a server's tool names."""
    declared, served = set(operations(tool)), set(served)
    return ([f"the server exposes '{n}', which {tool['id']} does not declare"
             for n in sorted(served - declared)] +
            [f"{tool['id']} declares '{n}', which the server does not expose"
             for n in sorted(declared - served)])


def server_target(tool: dict, root: str | pathlib.Path, traceparent: str | None = None) -> Any:
    """What ``mcp.Client`` connects to for this artifact: stdio parameters or an HTTP
    transport. ``command: python`` means the interpreter running KeelSpec, so a
    server starts in the same environment rather than whatever ``python`` is on PATH."""
    server = tool.get("server") if isinstance(tool.get("server"), dict) else {}
    transport = tool.get("transport") or "stdio"
    if transport == "stdio":
        from mcp.client.stdio import StdioServerParameters
        command = server.get("command")
        if not command:
            raise ToolError(f"{tool['id']} declares no server.command")
        if command in ("python", "python3"):
            command = sys.executable
        cwd = pathlib.Path(root) / str(server.get("cwd") or ".")
        env = {str(k): str(v) for k, v in (server.get("env") or {}).items()}
        return StdioServerParameters(command=command, args=[str(a) for a in server.get("args") or []],
                                     env=env or None, cwd=str(cwd))
    if transport == "http":
        url = server.get("url")
        if not url:
            raise ToolError(f"{tool['id']} declares no server.url")
        import httpx2
        from mcp.client.streamable_http import streamable_http_client
        headers = {str(k): str(v) for k, v in (server.get("headers") or {}).items()}
        if traceparent:
            headers["traceparent"] = traceparent
        return streamable_http_client(url, http_client=httpx2.AsyncClient(headers=headers))
    raise ToolError(f"{tool['id']} has unknown transport {transport!r}")


def result_data(result: Any) -> Any:
    """A CallToolResult as plain data: structured content when the server gives it,
    else the text content, parsed as JSON when it is JSON."""
    texts = [c.text for c in (result.content or []) if getattr(c, "type", None) == "text"]
    if result.is_error:
        raise ToolError("; ".join(texts) or "the tool reported an error")
    structured = result.structured_content
    if structured is not None:
        # Servers wrap a non-object return value as {"result": value}.
        if isinstance(structured, dict) and list(structured) == ["result"]:
            return structured["result"]
        return structured
    joined = "\n".join(texts)
    try:
        return json.loads(joined)
    except ValueError:
        return joined


class MCPExecutor:
    """A ``ToolExecutor`` backed by MCP sessions.

    The agent loop is synchronous and the SDK is async, so one background event loop
    (an anyio blocking portal) runs the sessions. Each tool's session lives in its own
    task for its whole life, because a session's task groups and cancel scopes must
    be entered and exited by the same task; calls reach it through a queue. Use as a
    context manager, or call ``close()``.

    ``connect`` maps a tool artifact to what ``mcp.Client`` connects to; the default
    is ``server_target``. Tests pass an in-process server instead.
    """

    def __init__(self, root: str | pathlib.Path = ".", *, traceparent: str | None = None,
                 connect: Callable[[dict], Any] | None = None,
                 open_timeout: float = OPEN_TIMEOUT_SECONDS):
        self.root = pathlib.Path(root)
        self.traceparent = traceparent
        self.connect = connect or (lambda tool: server_target(tool, self.root, self.traceparent))
        self.open_timeout = open_timeout
        self.calls: list[tuple[str, str]] = []
        self._sessions: dict[str, tuple[Any, Any]] = {}   # tool id -> (send, task future)
        self._portal_cm = None
        self._portal = None

    # ── lifecycle ────────────────────────────────────────────────────────────
    def __enter__(self) -> MCPExecutor:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _portal_(self):
        if self._portal is None:
            from anyio.from_thread import start_blocking_portal
            self._portal_cm = start_blocking_portal()
            self._portal = self._portal_cm.__enter__()
        return self._portal

    def close(self) -> None:
        if self._portal is None:
            return
        try:
            for send, task in self._sessions.values():
                self._portal.call(send.aclose)
                with contextlib.suppress(Exception):
                    task.result()
        finally:
            self._sessions.clear()
            self._portal_cm.__exit__(None, None, None)
            self._portal = self._portal_cm = None

    # ── sessions ─────────────────────────────────────────────────────────────
    async def _session(self, tool: dict, receive, task_status) -> None:
        """Own one tool's session: open it, check it for drift, then serve calls."""
        import anyio
        from mcp import Client
        target = self.connect(tool)
        problems: list[str] = []
        try:
            with anyio.CancelScope(deadline=anyio.current_time() + self.open_timeout) as scope:
                async with Client(target) as client:
                    listed = await client.list_tools()
                    problems = drift(tool, [t.name for t in listed.tools])
                    # On drift, leave the session first and raise below: raised in
                    # here, it would surface wrapped in the session's exception group.
                    if not problems:
                        scope.deadline = math.inf   # the deadline was for opening only
                        task_status.started()
                        async with receive:
                            async for job, future in receive:
                                try:
                                    future.set_result(await job(client))
                                except Exception as exc:  # back to the calling thread
                                    future.set_exception(exc)
                                except BaseException:
                                    # Cancelled (the transport died): never leave
                                    # the caller waiting on a future nobody sets.
                                    future.set_exception(ToolError(
                                        f"{tool['id']}: the server connection was lost"))
                                    raise
        except Exception as exc:
            raise ToolError(f"{tool['id']}: cannot reach the server: {exc}") from exc
        if problems:
            raise ToolDrift(tool["id"], problems)
        if scope.cancelled_caught:
            raise ToolError(f"{tool['id']}: the server did not start within "
                            f"{self.open_timeout:g}s")

    def open(self, tool: dict) -> None:
        """Open (and drift-check) a tool's session now rather than on first call, so
        a run refuses to start against a drifted server (PAC-073)."""
        if tool["id"] in self._sessions:
            return
        import anyio
        portal = self._portal_()
        send, receive = portal.call(lambda: _stream_pair(anyio))
        task, _ = portal.start_task(self._session, tool, receive)
        self._sessions[tool["id"]] = (send, task)

    def _submit(self, tool: dict, job: Callable[[Any], Any]) -> Any:
        self.open(tool)
        send, _ = self._sessions[tool["id"]]
        future: concurrent.futures.Future = concurrent.futures.Future()
        self._portal.call(send.send, (job, future))
        return future.result()

    def tool_names(self, tool: dict) -> list[str]:
        """The server's tool names, without the drift check (``tools check`` reports
        drift itself, as diagnostics rather than an exception)."""
        async def job():
            import anyio
            from mcp import Client
            with anyio.fail_after(self.open_timeout):
                async with Client(self.connect(tool)) as client:
                    listed = await client.list_tools()
            return sorted(t.name for t in listed.tools)
        try:
            return self._portal_().call(job)
        except ToolError:
            raise
        except TimeoutError as exc:
            raise ToolError(f"{tool['id']}: the server did not answer within "
                            f"{self.open_timeout:g}s") from exc
        except Exception as exc:
            raise ToolError(f"{tool['id']}: cannot reach the server: {exc}") from exc

    def call(self, tool: dict, operation: str, args: dict) -> Any:
        self.calls.append((tool["id"], operation))
        timeout = float(tool.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)

        async def job(client):
            import anyio
            try:
                with anyio.fail_after(timeout):
                    result = await client.call_tool(operation, args)
            except (TimeoutError, ToolError):
                raise
            except Exception as exc:  # protocol or transport failure: an error step
                raise ToolError(f"{tool['id']}.{operation}: {exc}") from exc
            return result_data(result)
        return self._submit(tool, job)


def _stream_pair(anyio):
    return anyio.create_memory_object_stream(math.inf)
