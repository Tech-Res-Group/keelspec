"""The KeelSpec config schema — ``product.config.yaml``.

A project declares its typed artifacts here. This is the seam that separates the
generic engine (loading, schema validation, cross-references, staleness) from a
project's own product model. Nothing about a specific domain lives in the engine.
"""
from __future__ import annotations

import pathlib

import yaml
from pydantic import BaseModel, Field


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
    # Fields captured into the bundle (beyond id/body). Unlisted fields are ignored.
    fields: list[str] = Field(default_factory=list)
    # field -> allowed values (a closed set). A value outside it is PAC-030.
    enums: dict[str, list[str]] = Field(default_factory=dict)
    # Cross-reference edges that must resolve (PAC-020).
    references: list[Reference] = Field(default_factory=list)


class Config(BaseModel):
    """A project's product-as-code configuration."""

    product_dir: str = "product"
    output: str = "build/product.generated.json"
    # Bundle key ordering. True (default) sorts keys for stable diffs; False keeps
    # insertion order — set it when a plugin's bundle_transformer builds a bespoke,
    # ordered bundle you need to reproduce byte-for-byte.
    sort_keys: bool = True
    types: list[ArtifactType]

    def type_by_name(self, name: str) -> ArtifactType | None:
        return next((t for t in self.types if t.name == name), None)


def load_config(path: str | pathlib.Path) -> Config:
    """Load and validate a product.config.yaml."""
    p = pathlib.Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return Config.model_validate(data)
