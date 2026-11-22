"""The KeelSpec config schema — ``product.config.yaml``.

A project declares its typed artifacts here. This is the seam that separates the
generic engine (loading, schema validation, cross-references, staleness) from a
project's own product model. Nothing about a specific domain lives in the engine.
"""
from __future__ import annotations

import pathlib

import yaml
from pydantic import BaseModel, Field, field_validator


class Reference(BaseModel):
    """A cross-reference edge: values of ``field`` on this type must resolve to the
    ``id`` of an artifact of type ``to``. ``field`` may be a scalar or a list."""

    field: str
    to: str


class ArtifactType(BaseModel):
    """One typed artifact collection — a directory of markdown-with-frontmatter files."""

    name: str  # collection name; also the key in the generated bundle
    dir: str  # subdirectory under product_dir
    # If set, every artifact id must start with this prefix AND (when
    # id_matches_filename) equal its filename stem.
    id_prefix: str | None = None
    id_matches_filename: bool = True
    # Frontmatter fields that must be present and non-empty (id is always required).
    required: list[str] = Field(default_factory=lambda: ["id"])
    # Fields that should be present but do not gate: a missing one is a PAC-002
    # warning. For the edge you want people to draw without blocking a draft --
    # a feature's link up to the outcome it serves, say.
    recommended: list[str] = Field(default_factory=list)
    # Fields captured into the bundle (beyond id/body). Unlisted fields are ignored.
    fields: list[str] = Field(default_factory=list)
    # field -> allowed values (a closed set). A value outside it is PAC-030.
    enums: dict[str, list[str]] = Field(default_factory=dict)
    # Cross-reference edges that must resolve (PAC-020).
    references: list[Reference] = Field(default_factory=list)


class RiskTier(BaseModel):
    """What a feature at this level of risk must go through.

    A tier is chosen by score, not by asking whether the work is "critical": the
    question that has a yes/no answer is rarely the one that predicts where a change
    hurts. Unset fields mean "the line's default", so a tier only states how it
    differs.
    """

    name: str
    min_score: int = 0
    # Roles that must each record an approval at the human gate before Design.
    approvers: list[str] = Field(default_factory=list)
    # Verify lenses to run, by name. None runs every lens.
    lenses: list[str] | None = None
    clean: bool | None = None
    max_repair: int | None = None
    # At least one critic must come from a different model vendor than the builder.
    # "Devin cannot credibly check Devin", as a rule rather than a note on the run.
    independent_critic: bool = False


class Delivery(BaseModel):
    """How the agent-built line treats a feature, decided from the feature itself.

    ``risk_factors`` maps a frontmatter field to the score each of its values adds
    (``customer_impact: {high: 3, medium: 1}``). A list-valued field adds the score
    of every value; ``true``/``false`` are matched as ``"true"``/``"false"``.
    ``tiers`` is checked highest ``min_score`` first; the first one the score
    reaches applies.
    """

    risk_factors: dict[str, dict[str, int]] = Field(default_factory=dict)
    tiers: list[RiskTier] = Field(default_factory=list)

    @field_validator("risk_factors", mode="before")
    @classmethod
    def _value_keys_are_strings(cls, value):
        # YAML reads an unquoted `false:` key as a boolean. Matching is on strings,
        # so normalise here rather than make every author remember to quote it.
        if not isinstance(value, dict):
            return value
        def key(k):
            return ("true" if k else "false") if isinstance(k, bool) else str(k)
        return {field: {key(k): v for k, v in (weights or {}).items()}
                for field, weights in value.items()}


class Price(BaseModel):
    """What one model costs, in USD per million tokens. Your contract's numbers, not
    list prices: KeelSpec ships none, so a cost it reports is one you supplied."""

    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: float | None = None
    cache_write_per_mtok: float | None = None


class Intake(BaseModel):
    """Where `keelspec intake` writes imported tickets, and how."""

    type: str = "features"
    # A frontmatter field to hold the ticket URL. Unset, the link lives in the body.
    link_field: str | None = None
    # The status a new draft gets. Unset: "idea" if allowed, else the first enum value.
    status: str | None = None


class Config(BaseModel):
    """A project's product-as-code configuration."""

    product_dir: str = "product"
    output: str = "build/product.generated.json"
    # Bundle key ordering. True (default) sorts keys for stable diffs; False keeps
    # insertion order — set it when a plugin's bundle_transformer builds a bespoke,
    # ordered bundle you need to reproduce byte-for-byte.
    sort_keys: bool = True
    types: list[ArtifactType]
    # Optional: the risk model `keelspec orchestrate` applies. Absent, every feature
    # runs the full line and the human gate asks for no particular role.
    delivery: Delivery | None = None
    # Optional: model id -> Price, for `keelspec runs` cost metrics. A call whose
    # model is absent (and whose vendor reported no cost) leaves its run unpriced.
    prices: dict[str, Price] = Field(default_factory=dict)
    # Optional: how `keelspec intake` maps tickets onto artifacts.
    intake: Intake | None = None

    def type_by_name(self, name: str) -> ArtifactType | None:
        return next((t for t in self.types if t.name == name), None)


def load_config(path: str | pathlib.Path) -> Config:
    """Load and validate a product.config.yaml."""
    p = pathlib.Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return Config.model_validate(data)
