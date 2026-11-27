"""Run budgets: steps, cost, wall clock and policy denials.

A budget that is hit stops the run with a typed outcome. Steps, cost and wall clock
end as ``budget_exceeded``; too many denials end as ``denied``, because an agent that
keeps reaching for forbidden tools is a behaviour to report, not a cost overrun.
"""
from __future__ import annotations

import dataclasses
import time

DEFAULTS = {"max_steps": 20, "max_cost_usd": None, "max_wall_seconds": 300, "max_denials": 3}


@dataclasses.dataclass
class Budgets:
    max_steps: int | None = 20
    max_cost_usd: float | None = None
    max_wall_seconds: float | None = 300
    max_denials: int | None = 3

    @classmethod
    def from_agent(cls, agent: dict) -> Budgets:
        declared = agent.get("budgets") if isinstance(agent.get("budgets"), dict) else {}
        return cls(**{k: declared.get(k, v) for k, v in DEFAULTS.items()})


@dataclasses.dataclass
class Usage:
    """What a run has spent so far. Survives a pause, so a resumed run keeps its count."""
    steps: int = 0
    cost_usd: float = 0.0
    denials: int = 0
    wall_seconds: float = 0.0
    started: float = dataclasses.field(default_factory=time.monotonic)

    def as_tuple(self) -> tuple[tuple[str, float], ...]:
        return (("cost_usd", round(self.cost_usd, 6)), ("denials", self.denials),
                ("steps", self.steps), ("wall_seconds", round(self.wall_seconds, 3)))


def exceeded(budgets: Budgets, usage: Usage) -> str | None:
    """The outcome a hit budget ends the run with, or None if every budget holds."""
    if budgets.max_denials is not None and usage.denials > budgets.max_denials:
        return "denied"
    if budgets.max_steps is not None and usage.steps >= budgets.max_steps:
        return "budget_exceeded"
    if budgets.max_cost_usd is not None and usage.cost_usd > budgets.max_cost_usd:
        return "budget_exceeded"
    if budgets.max_wall_seconds is not None and usage.wall_seconds > budgets.max_wall_seconds:
        return "budget_exceeded"
    return None
