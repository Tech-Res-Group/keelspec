"""Station runners — where the model actually gets called.

The orchestrator owns control flow; a runner owns one step's reasoning. Keeping
them apart is the spec's second principle, and it is why the pipeline is testable
without a network: swap `ClaudeRunner` for `StubRunner` and the wiring is unchanged.

`anthropic` is an optional dependency. KeelSpec's core job is validation, and a
missing SDK must not stop `keelspec validate` from running in CI.
"""
from __future__ import annotations

import json
import os
from typing import Any

from .orchestration import Station

SYSTEM = """\
You are one station on an agent-built software lifecycle.

The rules of the line:
- You own exactly one column of the work. Do not do another station's job.
- Return the structured result you were asked for and nothing else.
- Never claim something was verified that you did not verify.
- You propose; a deterministic gate judges and a human merges. You cannot ship.

Product intent is versioned source and the rubric already exists. You are labour
against it, not an author of it."""


_UNSET: Any = object()


def resolve_thinking(explicit: Any = _UNSET) -> dict | None:
    """The Anthropic ``thinking`` config to send, or ``None`` to omit the param.

    Not every model supports extended thinking — Haiku, in particular, rejects
    ``{"type": "adaptive"}`` with a 400 — so this must be controllable rather than
    hard-wired on. Precedence: an explicit value passed to the runner (including an
    explicit ``None``) wins; otherwise the ``KEELSPEC_THINKING`` env var; otherwise
    adaptive. Accepted env values: ``adaptive`` (default), ``off``/``none``/``0``/``""``
    to omit, or ``enabled:<budget_tokens>`` for fixed-budget extended thinking.
    """
    if explicit is not _UNSET:
        return explicit
    raw = os.getenv("KEELSPEC_THINKING", "adaptive").strip().lower()
    if raw in ("", "off", "none", "no", "0", "false"):
        return None
    if raw.startswith("enabled"):
        _, _, budget = raw.partition(":")
        try:
            return {"type": "enabled", "budget_tokens": int(budget)}
        except ValueError:
            return {"type": "enabled", "budget_tokens": 8000}
    return {"type": "adaptive"}


def _strip_unsupported(kwargs: dict, message: str) -> bool:
    """Remove the one param a model-unsupported 400 names from ``kwargs``, in place.

    The roster sends a couple of params uniformly that not every model accepts —
    ``thinking`` (top level) and an ``effort`` knob inside ``output_config`` — and a
    model that lacks one 400s with a message naming it ("...does not support the
    effort parameter", "adaptive thinking is not supported..."). Returns True if it
    stripped something (so the caller should retry), False if the error is about
    something we can't fix by dropping a param (so the caller should re-raise).
    """
    msg = message.lower()
    if "thinking" in msg and "thinking" in kwargs:
        del kwargs["thinking"]
        return True
    if "effort" in msg and isinstance(kwargs.get("output_config"), dict) \
            and "effort" in kwargs["output_config"]:
        # Drop only `effort`; keep the rest of output_config (e.g. the json_schema format).
        oc = dict(kwargs["output_config"])
        oc.pop("effort")
        kwargs["output_config"] = oc
        return True
    return False


def create_message(client: Any, base_kwargs: dict, thinking: dict | None = None) -> Any:
    """``messages.create`` that strips a model-unsupported param and retries.

    A station on a model that rejects a uniformly-sent param (e.g. the Haiku
    ``Understand`` station rejects both ``thinking`` and ``effort``) would otherwise
    400 and sink the whole run at step one. On such a 400 we strip the named param
    and retry — bounded, and only for params we know how to drop; any other error
    propagates unchanged. Stateless: each call degrades independently, so an
    Opus station still gets full thinking even after a Haiku station degraded.
    """
    kwargs = dict(base_kwargs)
    if thinking is not None:
        kwargs["thinking"] = thinking
    last_exc: Exception | None = None
    for _ in range(3):   # at most: strip thinking, then strip effort, then succeed
        try:
            return client.messages.create(**kwargs)
        except Exception as exc:  # narrowed by message below; the SDK type is optional
            last_exc = exc
            if not _strip_unsupported(kwargs, str(exc)):
                raise
    raise last_exc  # exhausted the strip budget; surface the last real error


class ClaudeRunner:
    """Runs a station as one structured Messages API call.

    Model and effort come from the station itself, so the cost/correctness dial is
    explicit per role rather than every station inheriting one default: a cheap
    model where the work is retrieval, the strongest tier where being
    confident-but-wrong is the failure that matters.
    """

    def __init__(self, api_key: str | None = None, *, max_tokens: int = 16000,
                 system: str = SYSTEM, thinking: Any = _UNSET):
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._max_tokens = max_tokens
        self._system = system
        self._thinking = resolve_thinking(thinking)
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set -- use --dry-run for the stub runner")
        try:
            import anthropic
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "the anthropic package is not installed: pip install 'keelspec[agents]'"
            ) from exc
        self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def run(self, station: Station, prompt: str, schema: dict | None = None) -> dict:
        client = self._get_client()

        output_config: dict[str, Any] = {"effort": station.effort or "high"}
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}

        base_kwargs = {
            "model": station.model or "claude-opus-5",
            "max_tokens": self._max_tokens,
            "system": self._system,
            "output_config": output_config,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = create_message(client, base_kwargs, self._thinking)

        if getattr(response, "stop_reason", None) == "refusal":
            raise RuntimeError(f"{station.id} refused by safety classifier")

        text = "".join(b.text for b in response.content if b.type == "text")
        if schema is None:
            return {"text": text}
        try:
            return json.loads(text)
        except ValueError as exc:
            raise RuntimeError(f"{station.id} returned unparseable JSON") from exc


# ── the cross-provider adversary ─────────────────────────────────────────────
# The structural break in the correlated-validation loop: a critic from a DIFFERENT
# model provider, so it cannot share the builder's blind spots. Diversity is a
# correctness lever, not a nicety.
#
# stdlib only, on purpose. `validate` must stay dependency-light, and this lens is
# opt-in via OPENROUTER_API_KEY -- with the key absent the run is byte-identical to
# native-only. A critic that cannot be reached ABSTAINS; it must never block a line.
CROSS_PROVIDER_LENS = "cross-provider(openrouter)"

_CROSS_SYSTEM = (
    "You are an adversarial code reviewer. Try to REFUTE the change -- default to "
    "refuted=true if you are not convinced it is correct and safe. Reply with STRICT "
    "JSON only, no prose and no markdown fences, matching exactly: "
    '{"lens":"' + CROSS_PROVIDER_LENS + '","refuted":<bool>,'
    '"severity":"blocker|major|minor|none",'
    '"reason":<string>,"failing_case":<string>}'
)


class CrossProviderLens:
    """One more verdict, from a non-Claude model routed through OpenRouter."""

    ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 timeout: float = 60.0):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.model = model or os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def verdict(self, context: str) -> dict:
        """Always returns a verdict-shaped dict. Never raises."""
        from .orchestration import Verdict

        if not self.enabled:
            return dataclasses_asdict(
                Verdict.benign(CROSS_PROVIDER_LENS, "OPENROUTER_API_KEY not set"))

        import urllib.error
        import urllib.request

        body = json.dumps({
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _CROSS_SYSTEM},
                {"role": "user", "content": context},
            ],
        }).encode()

        request = urllib.request.Request(
            self.ENDPOINT, data=body, method="POST",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode())
            content = payload["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError) as exc:
            return dataclasses_asdict(
                Verdict.benign(CROSS_PROVIDER_LENS, f"{type(exc).__name__}"))

        data["lens"] = CROSS_PROVIDER_LENS
        return data


def dataclasses_asdict(obj) -> dict:
    import dataclasses
    return dataclasses.asdict(obj)


# ── OpenAI-compatible runner: the config bridge to any chat-completions gateway ──
# keelspec's native runners speak the Anthropic Messages API. This one speaks the
# OpenAI ``/chat/completions`` shape, so the pipeline can be pointed — by ``base_url`` —
# at ANY OpenAI-compatible endpoint: a routing gateway (e.g. Muchty), OpenRouter, a
# local vLLM/Ollama, or OpenAI itself. That is what turns "no config bridge" into a
# base_url. stdlib-only, matching CrossProviderLens — no SDK dependency.

def openai_chat(base_url: str, api_key: str, body: dict, timeout: float = 120.0,
                extra_headers: dict | None = None) -> tuple[dict, str | None]:
    """POST one OpenAI chat-completions request. Returns ``(payload, served_model)`` —
    the served model is read from a gateway header when present (``x-muchty-model``).

    On an HTTP error the gateway's response *body* is surfaced in the raised message: a
    bare ``502 Bad Gateway`` is useless for debugging a routing gateway, whereas the body
    usually names the real cause (an upstream/BYOK failure, a too-large ``max_tokens``, an
    unsupported param). Truncated so a runaway body can't flood a log."""
    import urllib.error
    import urllib.request
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update({k: v for k, v in extra_headers.items() if v})
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            served = resp.headers.get("x-muchty-model") or resp.headers.get("x-model")
            return json.loads(resp.read().decode()), served
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:600]
        except Exception:
            detail = exc.reason or ""
        raise RuntimeError(f"gateway {exc.code} from {url}: {detail}") from exc


_JSON_ONLY = ("\n\nIMPORTANT: reply with ONE JSON object matching the requested schema and "
              "nothing else — no prose, no explanation, no markdown code fences.")


def extract_json_object(text: str) -> Any:
    """Parse a JSON object out of a model's text reply, tolerating a ```json fence or a
    little surrounding prose — so this works across gateway-routed models that don't honour
    a strict json_object response_format. Raises ValueError if no object can be recovered."""
    t = text.strip()
    if t.startswith("```"):
        nl = t.find("\n")
        t = (t[nl + 1:] if nl != -1 else t[3:])
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
        t = t.strip()
    try:
        return json.loads(t)
    except ValueError:
        i, j = t.find("{"), t.rfind("}")
        if 0 <= i < j:
            return json.loads(t[i:j + 1])  # outermost { … } as a last resort
        raise


# Station id -> concept, for a gateway that routes by what KIND of work a request is
# rather than by a model name. Every station is a different job — ST-01 reads a graph,
# ST-03 designs, ST-06 tries to refute — and the ROSTER's `model` column is a policy
# table written in Python. Handing the station's concept to a router moves that policy
# into the router's config, where it can be reviewed and changed without a release.
#
# The names on the right belong to the ROUTER OPERATOR's catalogue, not to this
# library, which is why this is a plain dict you pass in and can replace wholesale.
# These match MuchtyRouter's shipped catalogue.
STATION_CONCEPTS = {
    "ST-01": "content.summarize",   # read the graph, report what it says
    "ST-03": "spec.disambiguate",   # design against an intent that may be underspecified
    "ST-04": "code.repair",         # write the change
    "ST-04b": "code.repair",        # simplify it without changing behaviour
    "ST-05": "code.repair",         # adversarial coverage
    "ST-06": "code.repair",         # four refuting lenses
}
DEFAULT_CONCEPT = "general.assist"


class OpenAIRunner:
    """Runs a station against any OpenAI-compatible chat-completions endpoint.

    Same ``run(station, prompt, schema)`` contract as ClaudeRunner, so it drops into the
    Orchestrator unchanged — but the reasoning runs through whatever ``base_url`` points
    at. Gateway routing/metadata (a concept header, a project tag) rides on
    ``extra_headers``. Structured stations get ``response_format=json_object``; the
    result is parsed from the message content.
    """

    def __init__(self, base_url: str, api_key: str | None = None, *, model: str = "auto",
                 system: str = SYSTEM, max_tokens: int = 8192, json_mode: bool = False,
                 temperature: float | None = None,
                 concepts: dict[str, str] | None = None,
                 concept_header: str = "x-muchty-concept",
                 extra_headers: dict | None = None, timeout: float = 120.0):
        self.base_url = base_url
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model
        self._system = system
        self._max_tokens = max_tokens
        self._json_mode = json_mode
        self._temperature = temperature
        self._extra_headers = dict(extra_headers or {})
        self._concepts = concepts
        self._concept_header = concept_header
        self.timeout = timeout

    def headers_for(self, station: Station) -> dict:
        """Headers for one station — its concept included when concept routing is on.

        ``extra_headers`` alone is constant for a whole run, so every station arrives
        at the gateway looking like the same kind of request. This varies the one
        header that says otherwise. Off unless ``concepts`` is passed, so the default
        request is byte-identical to before.
        """
        headers = dict(self._extra_headers)
        if self._concepts is not None:
            headers[self._concept_header] = self._concepts.get(station.id, DEFAULT_CONCEPT)
        return headers

    def run(self, station: Station, prompt: str, schema: dict | None = None) -> dict:
        # For a structured station, ASK for JSON in the prompt rather than relying on
        # `response_format`: many gateway-routed providers reject the OpenAI json_object
        # param (Anthropic via a gateway returns a 400), so a prompt instruction is the
        # portable path. Opt into strict json_object with `json_mode=True` when the
        # endpoint supports it (e.g. OpenAI proper).
        user = prompt + _JSON_ONLY if (schema is not None and not self._json_mode) else prompt
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": "system", "content": self._system},
                {"role": "user", "content": user},
            ],
        }
        # `temperature` is OFF by default: newer models (the Claude 5 family) reject it as
        # a deprecated param with a 400, and it isn't needed for structured stations. Pass
        # temperature=<n> explicitly for an endpoint/model that still wants it.
        if self._temperature is not None:
            body["temperature"] = self._temperature
        if schema is not None and self._json_mode:
            body["response_format"] = {"type": "json_object"}
        payload, _served = openai_chat(self.base_url, self._api_key, body, self.timeout,
                                       self.headers_for(station))
        try:
            text = payload["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"{station.id}: malformed response from {self.base_url}") from exc
        if schema is None:
            return {"text": text}
        try:
            data = extract_json_object(text)
        except ValueError as exc:
            raise RuntimeError(
                f"{station.id} returned unparseable JSON (first 200 chars: {text[:200]!r})") from exc
        # A station result must be a JSON OBJECT. A smaller/gateway-routed model sometimes
        # returns a bare string or list; guard it so the downstream station gets a clear
        # error instead of an opaque "'str' has no .get".
        if not isinstance(data, dict):
            raise RuntimeError(
                f"{station.id} returned a non-object JSON ({type(data).__name__}); the routed "
                f"model did not return an object (first 200 chars: {text[:200]!r})")
        return data
