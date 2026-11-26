"""Load the compiled bundle the runtime executes (invariant I-10).

The runtime runs ``product.generated.json``, never the markdown. Before it starts it
asks ``validate`` -- the one judge -- and refuses (PAC-079) if there is any error,
including a stale bundle (PAC-060), or if the agents preset is not enabled.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

from ..config import Config
from ..engine import validate


class BundleRefused(RuntimeError):
    """PAC-079: the runtime will not start against this bundle."""


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def load_bundle(config: Config, root: str | pathlib.Path = ".", config_path: str | None = None,
                registry=None) -> tuple[dict, dict]:
    """The committed bundle and its provenance, or BundleRefused."""
    root = pathlib.Path(root)
    if "agents" not in config.presets:
        raise BundleRefused("PAC-079 product.config.yaml does not enable `presets: [agents]`; "
                            "there are no agents to run")
    report = validate(config, root, registry)
    if report.errors:
        shown = "; ".join(d.render() for d in report.errors[:5])
        more = f" (+{len(report.errors) - 5} more)" if len(report.errors) > 5 else ""
        raise BundleRefused(f"PAC-079 the bundle fails validation: {shown}{more}")
    out = root / config.output
    bundle = json.loads(out.read_text(encoding="utf-8"))
    cfg = root / (config_path or "product.config.yaml")
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                                text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = ""
    return bundle, {"bundle_sha256": sha256(out), "config_sha256": sha256(cfg),
                    "git_commit": commit}
