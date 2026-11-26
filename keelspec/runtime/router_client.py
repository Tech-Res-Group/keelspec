"""The router client: FifeRouter, or any OpenAI-compatible endpoint, over HTTP.

FifeRouter is a service, never an import (invariant I-7): this module speaks HTTP to
``{base_url}/chat/completions`` and nothing else. Per call it sends:

- ``x-fife-concept``  the agent's concept (``moneypath.verify``)
- ``x-fife-session``  the run id, so the router can keep a run on one model
- ``x-fife-critical`` ``true`` for an agent with ``criticality: high``
- ``traceparent``     W3C trace context, so router logs join KeelSpec spans

and reads back ``x-fife-model`` (what actually served), ``x-fife-rung`` and
``x-fife-attempts``.

A refusal is never a silent downgrade (I-9). 402, 422 and 502 raise ``RouterRefusal``
at once, with no retry and no weaker model: the run stops at that step with a typed
outcome. Only transport errors and other 5xx are retried, at most twice, with jitter.
"""
from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import random
import re
import time
from typing import Any

import yaml

REFUSALS = {402: "spend_cap", 422: "no_compliant_model", 502: "chain_exhausted"}
MAX_RETRIES = 2
NAME_SEP = "__"


class RouterRefusal(RuntimeError):
    """The router refused (402/422/502). Not retried."""

    def __init__(self, kind: str, status: int, detail: str = ""):
        super().__init__(f"router refused ({status} {kind}){': ' + detail if detail else ''}")
        self.kind, self.status = kind, status


class RouterError(RuntimeError):
    """Transport failure or a malformed response, after retries."""


@dataclasses.dataclass
class RouterSettings:
    base_url: str = "https://api.fiferouter.com/v1"
    api_key_env: str = "FIFEROUTER_API_KEY"
    timeout_seconds: float = 60.0
    model: str = "auto"


@dataclasses.dataclass
class RuntimeSettings:
    router: RouterSettings = dataclasses.field(default_factory=RouterSettings)
    capture_content: bool = False

    @classmethod
    def load(cls, path: str | pathlib.Path | None) -> RuntimeSettings:
        """``keelspec.runtime.yaml`` (router + telemetry), or the defaults."""
        data: dict = {}
        if path and pathlib.Path(path).exists():
            data = yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8")) or {}
        router = {k: v for k, v in (data.get("router") or {}).items()
                  if k in {f.name for f in dataclasses.fields(RouterSettings)}}
        telemetry = data.get("telemetry") or {}
        return cls(RouterSettings(**router), bool(telemetry.get("capture_content", False)))


@dataclasses.dataclass(frozen=True)
class RouterReply:
    message: dict                 # the assistant message: content and/or tool_calls
    served_model: str | None
    rung: str | None
    attempts: int | None
    concept: str | None
    input_tokens: int | None
    output_tokens: int | None


# ── tool names ───────────────────────────────────────────────────────────────
def tool_name(tool_id: str, operation: str) -> str:
    """An OpenAI function name for TOOL-x.op. Dots are not allowed, so `__` joins them."""
    name = f"{tool_id}{NAME_SEP}{operation}"
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise ValueError(f"{tool_id}.{operation} cannot be expressed as a function name")
    return name


def parse_tool_name(name: str) -> tuple[str, str]:
    tool_id, sep, operation = name.partition(NAME_SEP)
    if not sep:
        raise ValueError(f"{name!r} is not a tool function name")
    return tool_id, operation


def to_openai_tool(tool_id: str, operation: str, description: str = "",
                   input_schema: dict | None = None) -> dict:
    """An MCP tool (name, description, inputSchema) as an OpenAI function definition."""
    schema = dict(input_schema) if isinstance(input_schema, dict) else {}
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    return {"type": "function", "function": {
        "name": tool_name(tool_id, operation),
        "description": (description or f"{tool_id}.{operation}")[:1024],
        "parameters": schema}}


def new_traceparent() -> str:
    return f"00-{random.getrandbits(128):032x}-{random.getrandbits(64):016x}-01"


# ── the client ───────────────────────────────────────────────────────────────
class RouterClient:
    def __init__(self, settings: RouterSettings | None = None, *, api_key: str | None = None,
                 transport: Any = None, sleep=time.sleep):
        self.settings = settings or RouterSettings()
        self.api_key = api_key if api_key is not None else os.getenv(self.settings.api_key_env, "")
        self._transport = transport
        self._sleep = sleep
        self.calls = 0

    def _client(self):
        import httpx
        return httpx.Client(base_url=self.settings.base_url.rstrip("/") + "/",
                            timeout=self.settings.timeout_seconds, transport=self._transport)

    def headers(self, concept: str, session: str, critical: bool, traceparent: str) -> dict:
        h = {"content-type": "application/json", "x-fife-concept": concept,
             "x-fife-session": session, "x-fife-critical": "true" if critical else "false",
             "traceparent": traceparent}
        if self.api_key:
            h["authorization"] = f"Bearer {self.api_key}"
        return h

    def _post(self, path: str, body: dict, headers: dict):
        import httpx
        last: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            self.calls += 1
            try:
                with self._client() as client:
                    response = client.post(path, content=json.dumps(body), headers=headers)
            except httpx.TransportError as exc:
                last = exc
            else:
                if response.status_code in REFUSALS:
                    raise RouterRefusal(REFUSALS[response.status_code], response.status_code,
                                        response.text[:300])
                if response.status_code >= 500:
                    last = RouterError(f"router {response.status_code}")
                elif response.status_code >= 400:
                    raise RouterError(f"router {response.status_code}: {response.text[:300]}")
                else:
                    return response
            if attempt < MAX_RETRIES:
                self._sleep(0.5 * (2 ** attempt) + random.random() * 0.25)
        raise RouterError(f"router unreachable after {MAX_RETRIES + 1} attempts: {last}")

    def chat(self, messages: list[dict], tools: list[dict], *, concept: str, session: str,
             critical: bool, traceparent: str) -> RouterReply:
        body: dict[str, Any] = {"model": self.settings.model, "messages": messages}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        response = self._post("chat/completions", body,
                              self.headers(concept, session, critical, traceparent))
        try:
            payload = response.json()
            message = payload["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RouterError(f"malformed router response: {exc}") from exc
        usage = payload.get("usage") or {}
        attempts = response.headers.get("x-fife-attempts")
        return RouterReply(
            message=message,
            served_model=response.headers.get("x-fife-model") or payload.get("model"),
            rung=response.headers.get("x-fife-rung"),
            attempts=int(attempts) if attempts and attempts.isdigit() else None,
            concept=response.headers.get("x-fife-concept") or concept,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"))

    def explain(self, messages: list[dict], tools: list[dict], *, concept: str, session: str,
                critical: bool, traceparent: str) -> dict:
        """FifeRouter's /v1/explain: the routing plan, without dispatching anything."""
        body = {"model": self.settings.model, "messages": messages, "tools": tools}
        response = self._post("explain", body,
                              self.headers(concept, session, critical, traceparent))
        return response.json()
