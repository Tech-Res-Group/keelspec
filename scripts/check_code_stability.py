#!/usr/bin/env python3
"""Compare this working copy's diagnostic codes against the last release on PyPI.

`CON-codes-are-an-api` promises that a released code keeps its meaning for the
life of the library, because consumers key CI allowlists, triage rules and
dashboards on the number. Until this script existed the promise was a convention:
nothing checked it, and the failure it guards against is invisible — an allowlist
keyed on a retired number stops matching in silence, and a suppression scoped to
one rule quietly moves to another.

Self-hosting makes that worse rather than better. A schema change and the tree
that satisfies it land in the same commit, so the repository's own gate always
agrees with the repository's own engine. The only way to notice a break is to ask
a *different* version.

── what is and is not checkable ────────────────────────────────────────────

Two things are mechanical, and they are the two that fail silently:

  * a released code that has vanished without being declared retired
  * a code declared retired that is being emitted again

A third is not. Whether a reworded message still means the same thing is a
judgement, so a changed message is reported and not failed — requiring byte
equality would fail on a typo fix and teach everyone to bypass the gate, which
costs more than the wording drift it would catch.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from types import ModuleType

PYPI_JSON = "https://pypi.org/pypi/keelspec/json"


class Outcome:
    """What the comparison found. Empty `broken` means the promise still holds."""

    def __init__(self) -> None:
        self.broken: list[str] = []
        self.notices: list[str] = []


def compare(released: dict[str, str], current: dict[str, str], retired: dict[str, str]) -> Outcome:
    """The whole rule, as a pure function so it can be tested without a network.

    `retired` is the escape hatch and the record at once: retiring a code is
    allowed, forgetting that you did is not.
    """
    out = Outcome()

    for code, meaning in sorted(released.items()):
        if code in current:
            if current[code] != meaning:
                out.notices.append(
                    f"{code} message changed\n    was: {meaning}\n    now: {current[code]}"
                )
            continue
        if code in retired:
            out.notices.append(f"{code} retired: {retired[code]}")
            continue
        out.broken.append(
            f"{code} was released meaning {meaning!r} and is now absent. "
            "Add it to RETIRED in keelspec/diagnostics.py — a number is burned, not reused."
        )

    for code in sorted(set(retired) & set(current)):
        out.broken.append(
            f"{code} is declared retired but is registered again meaning "
            f"{current[code]!r}. A retired number is never reassigned."
        )

    for code in sorted(set(current) - set(released)):
        out.notices.append(f"{code} is new: {current[code]}")

    return out


def latest_released_version(timeout: float = 20.0) -> str | None:
    """The newest version on PyPI, or None when there is nothing to compare to."""
    try:
        with urllib.request.urlopen(PYPI_JSON, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))["info"]["version"]
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def _load_released_diagnostics(version: str, into: Path) -> ModuleType:
    """Install one released wheel and import its diagnostics module from there.

    `--no-deps` and `--target` rather than a virtualenv: the module imports only
    the standard library, so there is nothing to resolve and nothing to activate.
    Importing it rather than parsing it means this check sees exactly what a
    consumer's `pip install` sees.
    """
    subprocess.run(
        [
            sys.executable, "-m", "pip", "install", "--quiet", "--no-deps",
            "--target", str(into), f"keelspec=={version}",
        ],
        check=True,
    )
    source = into / "keelspec" / "diagnostics.py"
    if not source.exists():
        raise SystemExit(f"keelspec {version} has no keelspec/diagnostics.py — cannot compare")

    spec = importlib.util.spec_from_file_location("keelspec_released_diagnostics", source)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {source}")
    module = importlib.util.module_from_spec(spec)
    # Registered before execution because @dataclass resolves its own class's
    # module out of sys.modules to look up type names. Without this the released
    # module raises AttributeError on import and the check reads as a break in the
    # release rather than a defect here.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        help="Released version to compare against. Defaults to the newest on PyPI.",
    )
    args = parser.parse_args()

    version = args.version or latest_released_version()
    if version is None:
        print("keelspec is not on PyPI yet — nothing to compare against.")
        return 0

    # Imported here rather than at module scope so `--help` works in a checkout
    # where the package is not installed.
    from keelspec.diagnostics import CODES, RETIRED

    with tempfile.TemporaryDirectory() as tmp:
        released = _load_released_diagnostics(version, Path(tmp))
        outcome = compare(dict(released.CODES), dict(CODES), dict(RETIRED))

    for notice in outcome.notices:
        print(f"  note: {notice}")

    if outcome.broken:
        print(f"\ncode stability: {len(outcome.broken)} break(s) against keelspec {version}\n")
        for break_ in outcome.broken:
            print(f"  ERROR {break_}")
        print("\nSee product/constraints/CON-codes-are-an-api.md.")
        return 1

    print(f"\ncode stability: clean against keelspec {version} ({len(CODES)} codes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
