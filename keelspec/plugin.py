"""The extension seam — how a project layers its own rules on the generic engine.

The core engine does loading + schema/id/reference/enum/staleness checks. Real
projects need more: cross-file checks (does this ``links.code`` path exist?), derived
bundle fields (reverse edges, rollups), extra generated outputs (a runtime catalogue),
and project-specific diagnostic codes. A **plugin** registers those without forking the
engine — which is what lets a rich project (e.g. a payments platform) migrate onto
KeelSpec with **no loss of functionality**.

A plugin is a Python module exposing ``register(registry)``::

    # product_hooks.py
    from keelspec import register as register_code

    def register(reg):
        register_code("PAC-900", "links.code path does not exist on disk")

        @reg.validator
        def code_paths_exist(bundle, config, root, report):
            ...  # report.add("PAC-900", ...)

        @reg.bundle_transformer
        def add_reverse_edges(bundle, config, root):
            ...  # mutate bundle in place

        reg.extra_output("build/catalogue.json", render_catalogue)  # + staleness-gated
"""
from __future__ import annotations

import importlib
import importlib.util
import pathlib
from collections.abc import Callable
from dataclasses import dataclass, field

# A validator receives the loaded bundle, the config, the root path, and the Report
# to append diagnostics to. A bundle_transformer mutates the bundle in place before
# it is written. An extra output renders a string for a committed generated file
# (staleness-gated exactly like the main bundle).
Validator = Callable[[dict, "object", pathlib.Path, "object"], None]
BundleTransformer = Callable[[dict, "object", pathlib.Path], None]
OutputRenderer = Callable[[dict, "object", pathlib.Path], str]


@dataclass
class Registry:
    validators: list[Validator] = field(default_factory=list)
    bundle_transformers: list[BundleTransformer] = field(default_factory=list)
    extra_outputs: list[tuple[str, OutputRenderer]] = field(default_factory=list)

    def validator(self, fn: Validator) -> Validator:
        self.validators.append(fn)
        return fn

    def bundle_transformer(self, fn: BundleTransformer) -> BundleTransformer:
        self.bundle_transformers.append(fn)
        return fn

    def extra_output(self, path: str, renderer: OutputRenderer) -> None:
        """Register an additional committed generated file, staleness-gated (PAC-060)."""
        self.extra_outputs.append((path, renderer))


def load_plugin(spec: str | None) -> Registry:
    """Load a plugin by dotted module name or file path; return its populated Registry.

    An empty/None spec yields an empty Registry (the pure-core behaviour)."""
    reg = Registry()
    if not spec:
        return reg
    p = pathlib.Path(spec)
    if p.suffix == ".py" and p.exists():
        mod_spec = importlib.util.spec_from_file_location("_keelspec_plugin", p)
        module = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(module)  # type: ignore[union-attr]
    else:
        module = importlib.import_module(spec)
    register = getattr(module, "register", None)
    if register is None:
        raise SystemExit(f"plugin '{spec}' has no register(registry) function")
    register(reg)
    return reg
