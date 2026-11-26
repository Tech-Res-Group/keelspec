"""Tool executors: how an allowed call actually runs.

``FixtureExecutor`` answers from a scenario's ``fixtures`` (``TOOL-x.op: result``),
so a run is deterministic and offline. ``keelspec run --fixtures SCN-x`` uses it, and
``keelspec simulate`` replays scenarios with it. The MCP client (milestone M8) is
the executor for real tool servers; both satisfy ``ToolExecutor``.
"""
from __future__ import annotations

from typing import Any, Protocol


class ToolError(RuntimeError):
    """The tool could not answer. The step records an error outcome."""


class ToolExecutor(Protocol):
    def call(self, tool: dict, operation: str, args: dict) -> Any:
        ...


class FixtureExecutor:
    def __init__(self, fixtures: dict[str, Any] | None = None):
        self.fixtures = dict(fixtures or {})
        self.calls: list[tuple[str, str]] = []

    @classmethod
    def from_scenario(cls, bundle: dict, scenario_id: str) -> FixtureExecutor:
        scn = next((s for s in bundle.get("scenarios", []) if s["id"] == scenario_id), None)
        if scn is None:
            raise KeyError(f"no scenario {scenario_id!r} in the bundle")
        return cls(scn.get("fixtures") or {})

    def call(self, tool: dict, operation: str, args: dict) -> Any:
        key = f"{tool['id']}.{operation}"
        self.calls.append((tool["id"], operation))
        if key not in self.fixtures:
            raise ToolError(f"no fixture for {key}")
        return self.fixtures[key]
