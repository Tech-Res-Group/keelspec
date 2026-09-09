"""``fastpdlc validate --watch`` — the gate, re-run on every save.

The cheapest fix for the loop that actually hurts: author a cross-reference, push,
wait for CI, discover you typed ``CON-residency-pen``. Nothing here is new
validation — it is the same :func:`fastpdlc.engine.validate` on a timer, which is the
point. A watcher with its own opinion about correctness would be a second judge.

Polling, not ``inotify``. A watcher is a convenience and the core keeps its two
dependencies; a product tree is tens to hundreds of small files, so a stat sweep
every 400 ms costs less than the machinery to avoid it.

This is **not** a gate. It never exits non-zero on a failing tree — CI runs plain
``validate`` for that. Its exit code answers "did the watcher stop cleanly?", so a
red tree you are actively fixing does not kill your terminal.
"""
from __future__ import annotations

import pathlib
import sys
import time

from .config import Config, load_config
from .engine import load, validate

INTERVAL = 0.4


def _fingerprint(config: Config, root: pathlib.Path, config_path: pathlib.Path) -> dict[str, float]:
    """Modification times for everything a verdict depends on.

    The generated bundle is included deliberately: ``PAC-060`` compares it against
    the tree, so a ``fastpdlc build`` in another terminal changes the answer here and
    the watcher should notice.
    """
    stamps: dict[str, float] = {}
    for path in (config_path, root / config.output):
        try:
            stamps[str(path)] = path.stat().st_mtime
        except OSError:
            stamps[str(path)] = 0.0
    product = root / config.product_dir
    if product.exists():
        for path in product.rglob("*.md"):
            try:
                stamps[str(path)] = path.stat().st_mtime
            except OSError:
                continue
    return stamps


def _run_once(config: Config, root: pathlib.Path, registry) -> tuple[int, int]:
    """Validate and print, exactly as the one-shot command does. Returns (errors, warnings)."""
    report = validate(config, root, registry)
    for w in report.warnings:
        print(f"WARN  {w.render()}")
    for e in report.errors:
        print(f"ERROR {e.render()}")

    try:
        counts = {name: len(recs) for name, recs in load(config, root).items()}
        summary = ", ".join(f"{n} {c}" for n, c in counts.items())
    except Exception as exc:
        summary = f"tree did not load: {exc}"

    stamp = time.strftime("%H:%M:%S")
    verdict = "clean" if report.ok else f"{len(report.errors)} error(s)"
    print(f"\n[{stamp}] {summary} — {verdict}, {len(report.warnings)} warning(s).")
    return len(report.errors), len(report.warnings)


def watch(
    config_path: str,
    root: str = ".",
    registry=None,
    interval: float = INTERVAL,
    ticks: int | None = None,
) -> int:
    """Validate on every change until interrupted.

    ``ticks`` bounds the loop for tests; ``None`` means run until Ctrl-C. The config
    is re-read each cycle, so editing ``product.config.yaml`` — adding a type, adding
    an enum value — takes effect without restarting the watcher.
    """
    root_path = pathlib.Path(root)
    cfg_path = pathlib.Path(config_path)
    print(f"fastpdlc: watching {root_path / '.'} — Ctrl-C to stop\n", file=sys.stderr)

    last: dict[str, float] | None = None
    seen = 0
    try:
        while ticks is None or seen < ticks:
            try:
                config = load_config(cfg_path)
            except Exception as exc:
                # A broken config is the one thing that stops us reading the tree at
                # all. Say so and keep waiting: it is almost always mid-edit.
                current = {str(cfg_path): cfg_path.stat().st_mtime if cfg_path.exists() else 0.0}
                if current != last:
                    print(f"ERROR cannot load {cfg_path}: {exc}")
                    last = current
                seen += 1
                if ticks is None:
                    time.sleep(interval)
                continue

            current = _fingerprint(config, root_path, cfg_path)
            if current != last:
                if last is not None:
                    print("\n" + "─" * 60)
                _run_once(config, root_path, registry)
                last = current
            seen += 1
            if ticks is None:
                time.sleep(interval)
    except KeyboardInterrupt:
        print("\nfastpdlc: stopped watching", file=sys.stderr)
    return 0
