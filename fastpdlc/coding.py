"""A code-writing runner for ST-04.

The reasoning stations only need one structured call. Develop is different: it has
to look at the tree and change it, which means tools and a loop.

This is deliberately a *small* coding agent, not a general one. It can read, write
and list files beneath one root, and nothing else — no shell, no network, no delete,
no rename. That is enough to implement a change and far short of what a general
agent can do to a machine, which matters because the thing driving it is a model.

Every path is resolved and checked against the root before any I/O, so `..`,
absolute paths and symlink escapes are refused rather than sanitised. The loop is
bounded; a run that will not converge stops and says so.

    from fastpdlc.coding import CodingRunner
    runner = CodingRunner(root=".", write=True)

`write=False` is the default: the agent sees the tree and proposes a diff without
touching anything. Opt in to letting a model edit your working tree.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Any

from .orchestration import DEVELOP_SCHEMA, Station

MAX_TURNS = 12
MAX_READ_BYTES = 200_000
MAX_WRITE_BYTES = 400_000

SYSTEM = """\
You are the Develop station on an agent-built lifecycle. Implement the design you \
are given, and nothing beyond it.

You have three tools: list_files, read_file, write_file. There is no shell, no \
network, and no way to delete or rename. Read before you write — never write a file \
whose current contents you have not seen.

Work in small steps. When the change is complete, stop calling tools and return the \
final structured result: the files you changed and a concise diff summary for the \
test engineer and the reviewers.

You cannot merge, and you cannot run tests. A separate station tests your work, four \
critics try to refute it, a deterministic gate judges it, and a human decides."""

TOOLS = [
    {
        "name": "list_files",
        "description": "List files beneath a directory, relative to the project root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "relative directory, '.' for root"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file, relative to the project root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a UTF-8 text file, relative to the project root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
]


class PathOutsideRoot(Exception):
    """The agent asked for something outside the sandbox."""


class Sandbox:
    """Confined file access. Every path goes through `resolve` before any I/O."""

    def __init__(self, root: str | pathlib.Path, write: bool = False):
        self.root = pathlib.Path(root).resolve()
        self.write_enabled = write
        self.written: list[str] = []
        self.read: list[str] = []

    def resolve(self, relative: str) -> pathlib.Path:
        candidate = pathlib.Path(relative)
        if candidate.is_absolute():
            raise PathOutsideRoot(f"absolute paths are refused: {relative}")
        # resolve() collapses .. and follows symlinks, so the containment check
        # below cannot be fooled by either.
        target = (self.root / candidate).resolve()
        if target != self.root and self.root not in target.parents:
            raise PathOutsideRoot(f"outside the project root: {relative}")
        return target

    def list_files(self, relative: str = ".") -> str:
        base = self.resolve(relative or ".")
        if not base.is_dir():
            return f"not a directory: {relative}"
        names = []
        for entry in sorted(base.iterdir()):
            if entry.name.startswith(".") or entry.name in {"__pycache__", "node_modules"}:
                continue
            names.append(entry.name + ("/" if entry.is_dir() else ""))
        return "\n".join(names) or "(empty)"

    def read_file(self, relative: str) -> str:
        target = self.resolve(relative)
        if not target.is_file():
            return f"no such file: {relative}"
        if target.stat().st_size > MAX_READ_BYTES:
            return f"file too large to read ({target.stat().st_size} bytes): {relative}"
        self.read.append(relative)
        return target.read_text(encoding="utf-8", errors="replace")

    def write_file(self, relative: str, content: str) -> str:
        if not self.write_enabled:
            # Proposing is still useful: the diff summary is the deliverable.
            self.written.append(relative)
            return (f"DRY RUN: not written. Recorded {relative} "
                    f"({len(content)} chars) as a proposed change.")
        if len(content.encode()) > MAX_WRITE_BYTES:
            return f"refused: content exceeds {MAX_WRITE_BYTES} bytes"
        target = self.resolve(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        self.written.append(relative)
        return f"wrote {relative} ({len(content)} chars)"


class CodingRunner:
    """Runs Develop as a bounded tool loop; every other station as one call."""

    def __init__(self, root: str | pathlib.Path = ".", *, write: bool = False,
                 api_key: str | None = None, max_turns: int = MAX_TURNS,
                 fallback: Any = None, model: str = "claude-opus-5",
                 thinking: Any = None):
        self.sandbox = Sandbox(root, write=write)
        self.max_turns = max_turns
        self.model = model
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._client: Any = None
        # Same thinking resolution + graceful-degrade path as ClaudeRunner, so a
        # non-thinking model here won't sink the tool loop either. `_UNSET` means
        # "resolve from FASTPDLC_THINKING"; an explicit value (incl. None) wins.
        from .runners import _UNSET, ClaudeRunner, resolve_thinking
        self._thinking = resolve_thinking(_UNSET if thinking is None else thinking)
        # Non-Develop stations do not need tools; delegate them (same thinking arg).
        self.fallback = fallback or ClaudeRunner(
            api_key=self._api_key, thinking=(_UNSET if thinking is None else thinking))

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        try:
            import anthropic
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "the anthropic package is not installed: pip install 'fastpdlc[agents]'"
            ) from exc
        self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def _dispatch(self, name: str, args: dict) -> str:
        try:
            if name == "list_files":
                return self.sandbox.list_files(args.get("path", "."))
            if name == "read_file":
                return self.sandbox.read_file(args["path"])
            if name == "write_file":
                return self.sandbox.write_file(args["path"], args.get("content", ""))
            return f"unknown tool: {name}"
        except PathOutsideRoot as exc:
            return f"REFUSED: {exc}"
        except (OSError, KeyError) as exc:
            return f"error: {exc}"

    def run(self, station: Station, prompt: str, schema: dict | None = None) -> dict:
        # Clean edits files exactly as Develop does, so it needs the same tools.
        if station.id not in ("ST-04", "ST-04b"):
            return self.fallback.run(station, prompt, schema)

        client = self._get_client()
        messages: list[dict] = [{"role": "user", "content": prompt}]

        from .runners import create_message
        for _turn in range(self.max_turns):
            base_kwargs = {
                "model": self.model,
                "max_tokens": 16000,
                "system": SYSTEM,
                "output_config": {"effort": station.effort or "high"},
                "tools": TOOLS,
                "messages": messages,
            }
            response = create_message(client, base_kwargs, self._thinking)
            if getattr(response, "stop_reason", None) == "refusal":
                raise RuntimeError(f"{station.id} refused by safety classifier")

            if response.stop_reason != "tool_use":
                break

            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": self._dispatch(block.name, block.input or {}),
                })
            # All tool results go back in ONE user message, or Claude learns to stop
            # calling tools in parallel.
            messages.append({"role": "user", "content": results})
        else:
            return {
                "files_changed": sorted(set(self.sandbox.written)),
                "diff_summary": (f"stopped after {self.max_turns} turns without "
                                 f"converging; treat this change as incomplete"),
                "self_notes": "turn limit reached",
            }

        # One more call, no tools, to get the structured result.
        messages.append({
            "role": "user",
            "content": "Return the final structured result for this change now.",
        })
        final = client.messages.create(
            model=self.model,
            max_tokens=8000,
            system=SYSTEM,
            output_config={"effort": "low",
                           "format": {"type": "json_schema",
                                      "schema": schema or DEVELOP_SCHEMA}},
            messages=messages,
        )
        text = "".join(b.text for b in final.content if b.type == "text")
        try:
            data = json.loads(text)
        except ValueError:
            data = {"files_changed": [], "diff_summary": text[:800]}

        # The sandbox is the source of truth about what actually changed -- not the
        # model's recollection of it.
        data["files_changed"] = sorted(set(self.sandbox.written))
        data.setdefault("self_notes", "")
        if not self.sandbox.write_enabled:
            data["self_notes"] += " (dry run: no files were written)"
        return data


# The same three tools, in the OpenAI function-calling shape (Anthropic uses input_schema;
# OpenAI nests name/description/parameters under `function`).
OPENAI_TOOLS = [
    {"type": "function", "function": {
        "name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
    for t in TOOLS
]


class OpenAICodingRunner(CodingRunner):
    """A CodingRunner against any OpenAI-compatible endpoint (a gateway like Muchty,
    OpenRouter, a local server, or OpenAI). Same Sandbox, same tools, same
    source-of-truth accounting as CodingRunner — but the Develop tool loop uses OpenAI
    function-calling instead of Anthropic tool-use blocks, so a build can be routed
    through a gateway purely by ``base_url``. Non-Develop stations delegate to an
    OpenAIRunner over the same endpoint.
    """

    def __init__(self, root: str | pathlib.Path = ".", *, write: bool = False,
                 base_url: str, api_key: str | None = None, model: str = "auto",
                 max_turns: int = MAX_TURNS, fallback: Any = None,
                 concepts: dict[str, str] | None = None,
                 concept_header: str = "x-muchty-concept",
                 extra_headers: dict | None = None, timeout: float = 120.0):
        self.sandbox = Sandbox(root, write=write)
        self.max_turns = max_turns
        self.model = model
        self.base_url = base_url
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._extra_headers = dict(extra_headers or {})
        self._timeout = timeout
        from .runners import OpenAIRunner
        self.fallback = fallback or OpenAIRunner(
            base_url=base_url, api_key=self._api_key, model=model,
            concepts=concepts, concept_header=concept_header,
            extra_headers=self._extra_headers, timeout=timeout)

    def _headers_for(self, station: Station) -> dict:
        """Develop runs its own loop instead of delegating, so it has to ask the
        fallback for the same headers the other stations would have been given."""
        getter = getattr(self.fallback, "headers_for", None)
        return getter(station) if callable(getter) else self._extra_headers

    def run(self, station: Station, prompt: str, schema: dict | None = None) -> dict:
        if station.id not in ("ST-04", "ST-04b"):
            return self.fallback.run(station, prompt, schema)

        from .runners import openai_chat
        messages: list[dict] = [{"role": "system", "content": SYSTEM},
                                {"role": "user", "content": prompt}]
        for _turn in range(self.max_turns):
            body = {"model": self.model, "max_tokens": 8192,
                    "tools": OPENAI_TOOLS, "tool_choice": "auto", "messages": messages}
            payload, _ = openai_chat(self.base_url, self._api_key, body, self._timeout, self._headers_for(station))
            msg = payload["choices"][0]["message"]
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                break
            messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls})
            for tc in tool_calls:
                fn = tc.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                messages.append({"role": "tool", "tool_call_id": tc.get("id"),
                                 "content": self._dispatch(fn.get("name", ""), args)})
        else:
            return {
                "files_changed": sorted(set(self.sandbox.written)),
                "diff_summary": (f"stopped after {self.max_turns} turns without "
                                 f"converging; treat this change as incomplete"),
                "self_notes": "turn limit reached",
            }

        # Converged — one more call, no tools, for the structured result. Ask for JSON in
        # the prompt (not response_format) so this works on gateway-routed providers that
        # reject the json_object param, and parse tolerantly.
        from .runners import extract_json_object
        messages.append({"role": "user",
                         "content": "Return the final structured result for this change now as ONE "
                                    "JSON object (files_changed, diff_summary, self_notes) — no prose, "
                                    "no markdown fences."})
        body = {"model": self.model, "max_tokens": 4096, "messages": messages}
        payload, _ = openai_chat(self.base_url, self._api_key, body, self._timeout, self._headers_for(station))
        text = payload["choices"][0]["message"].get("content") or ""
        try:
            data = extract_json_object(text)
            if not isinstance(data, dict):
                data = {"files_changed": [], "diff_summary": str(data)[:800]}
        except ValueError:
            data = {"files_changed": [], "diff_summary": text[:800]}
        data["files_changed"] = sorted(set(self.sandbox.written))
        data.setdefault("self_notes", "")
        if not self.sandbox.write_enabled:
            data["self_notes"] += " (dry run: no files were written)"
        return data
