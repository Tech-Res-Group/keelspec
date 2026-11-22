"""Risk tiers: how much line a feature gets, decided from the feature itself.

"Critical or money-path work takes the full line; everything else may take a
shortcut" is a yes/no question asked of something that is not yes/no. Customer
impact, regulatory exposure, data sensitivity, irreversibility and dependency count
each move the risk, and a change can be off the money path and still be the one
that cannot be rolled back.

So the project declares which frontmatter fields count and by how much
(``delivery.risk_factors`` in ``product.config.yaml``), and each tier states what a
feature at that level must go through: which Verify lenses run, which roles must
accept the spec, how many repair rounds it gets. The score and every contribution
to it are recorded on the run, so "why did this get the light path?" has an answer
on file.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from .config import Config, Delivery, RiskTier


@dataclasses.dataclass(frozen=True)
class Assessment:
    score: int
    tier: RiskTier | None
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "tier": self.tier.name if self.tier else "",
                "reasons": list(self.reasons)}

    def orchestrator_options(self) -> dict[str, Any]:
        """Keyword arguments for :class:`~keelspec.orchestration.Orchestrator`.
        A tier field left unset falls through to the line's default."""
        opts: dict[str, Any] = {"risk": self.to_dict()}
        if self.tier is None:
            return opts
        opts["required_approvers"] = list(self.tier.approvers)
        if self.tier.lenses is not None:
            opts["lenses"] = list(self.tier.lenses)
        if self.tier.clean is not None:
            opts["clean"] = self.tier.clean
        if self.tier.max_repair is not None:
            opts["max_repair"] = self.tier.max_repair
        return opts


def _key(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def score(delivery: Delivery, record: dict) -> tuple[int, list[str]]:
    total, reasons = 0, []
    for field, weights in delivery.risk_factors.items():
        raw = record.get(field)
        for value in raw if isinstance(raw, list) else [raw]:
            if value is None:
                continue
            points = weights.get(_key(value), 0)
            if points:
                total += points
                reasons.append(f"{field}={_key(value)} (+{points})")
    return total, reasons


def assess(delivery: Delivery | None, record: dict | None) -> Assessment:
    """Score a record and pick its tier.

    An artifact that cannot be found is assessed at the HIGHEST tier: not knowing
    the risk of a change is not evidence that it is low. A score below every tier's
    ``min_score`` gets the lowest tier.
    """
    if delivery is None or not delivery.tiers:
        return Assessment(0, None)
    ordered = sorted(delivery.tiers, key=lambda t: t.min_score, reverse=True)
    if record is None:
        return Assessment(ordered[0].min_score, ordered[0],
                          ("artifact not found in the graph: assessed at the highest tier",))
    total, reasons = score(delivery, record)
    tier = next((t for t in ordered if total >= t.min_score), ordered[-1])
    return Assessment(total, tier, tuple(reasons))


def find(bundle: dict[str, list[dict]], artifact_id: str) -> dict | None:
    """The first record with this id in any collection."""
    for records in bundle.values():
        if not isinstance(records, list):
            continue
        for rec in records:
            if isinstance(rec, dict) and rec.get("id") == artifact_id:
                return rec
    return None


def assess_artifact(config: Config, bundle: dict[str, list[dict]],
                    artifact_id: str) -> Assessment:
    return assess(config.delivery, find(bundle, artifact_id))
