"""The ``keelspec`` command line: build | validate.

    keelspec build                       # regenerate the JSON bundle
    keelspec validate                    # schema + graph + staleness (CI gate)
    keelspec validate --watch            # the same gate, on every save
    keelspec evidence -o build/ev.json   # content-addressed audit record
    keelspec lsp                         # language server, on stdio
    keelspec mcp                         # the graph as tools, for an agent
    keelspec -c product.config.yaml -p product_hooks.py validate

Exit code is non-zero iff validation found errors — wire ``keelspec validate`` into CI.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from . import engine, evidence, orchestration
from .config import load_config
from .plugin import load_plugin


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="keelspec", description="Product-as-code as a validated graph.")
    p.add_argument("-c", "--config", default="product.config.yaml", help="path to product.config.yaml")
    p.add_argument("-C", "--root", default=".", help="project root (paths are resolved from here)")
    p.add_argument("-p", "--plugin", default=None, help="project plugin module or .py file")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="regenerate the committed JSON bundle(s)")
    val = sub.add_parser("validate", help="schema + graph + staleness checks (CI gate)")
    val.add_argument("--json", action="store_true", dest="as_json",
                     help="emit findings as JSON — codes are an API, so make them parseable")
    val.add_argument("--watch", action="store_true",
                     help="re-validate on every change until interrupted (not a gate)")
    ev = sub.add_parser(
        "evidence",
        help="emit a content-addressed record of what was checked, when, and on what",
    )
    ev.add_argument("-o", "--output", default=None,
                    help="write the record here instead of stdout")
    ev.add_argument("--verify", metavar="RECORD", default=None,
                    help="recompute the digests in an existing record instead of making one")

    sub.add_parser("lsp", help="run the language server on stdio (needs keelspec[lsp])")
    sub.add_parser("mcp", help="serve the product graph over MCP on stdio (needs keelspec[mcp])")

    orc = sub.add_parser(
        "orchestrate",
        help="run the agent-built lifecycle over one artifact (ST-01..ST-06)",
    )
    orc.add_argument("feature", help="the artifact id to build, e.g. FEAT-refunds")
    orc.add_argument("--dry-run", action="store_true",
                     help="use the offline stub runner: exercises the pipeline, calls no model")
    orc.add_argument("--resolve", action="append", default=[], metavar="ID=ANSWER",
                     help="answer a Disambiguate question (repeatable)")
    orc.add_argument("--max-repair", type=int, default=None,
                     help=f"bounded repair rounds (default {orchestration.Orchestrator.MAX_REPAIR})")
    orc.add_argument("--write", action="store_true",
                     help="let the Develop station actually edit files (default: propose only)")
    orc.add_argument("--no-clean", action="store_true",
                     help="skip ST-04b Clean (one fewer model call per run)")
    orc.add_argument("--cross-provider", action="store_true",
                     help="add a non-Claude critic via OpenRouter (needs OPENROUTER_API_KEY)")
    orc.add_argument("-o", "--output", default=None,
                     help="write the run report here instead of stdout")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config_path = f"{args.root}/{args.config}" if args.root != "." else args.config
    config = load_config(config_path)
    registry = load_plugin(args.plugin)

    if args.cmd == "validate" and args.watch:
        if args.as_json:
            # A tick-per-document JSON stream is not a format anything consumes.
            # Editors want the language server; CI wants one-shot --json.
            print("--watch and --json are mutually exclusive", file=sys.stderr)
            return 2
        from .watch import watch
        return watch(config_path, args.root, registry)

    if args.cmd == "lsp":
        from .lsp import serve
        return serve(args.config, args.root, args.plugin)

    if args.cmd == "mcp":
        from .mcp import serve
        return serve(args.config, args.root, args.plugin)

    if args.cmd == "build":
        for path in engine.build(config, args.root, registry):
            print(f"wrote {path}")
        return 0

    if args.cmd == "orchestrate":
        resolutions = {}
        for pair in args.resolve:
            key, _, value = pair.partition("=")
            if not value:
                print(f"--resolve expects ID=ANSWER, got: {pair}", file=sys.stderr)
                return 2
            resolutions[key.strip()] = value.strip()

        if args.dry_run:
            runner = orchestration.StubRunner()
        else:
            # Develop needs tools; every other station is one structured call.
            from .coding import CodingRunner
            runner = CodingRunner(root=args.root, write=args.write)

        extra_lens = None
        if args.cross_provider:
            from .runners import CrossProviderLens
            lens = CrossProviderLens()
            if not lens.enabled:
                print("cross-provider lens skipped: OPENROUTER_API_KEY not set",
                      file=sys.stderr)
            else:
                extra_lens = lens.verdict

        # The human gate as a file: answers a person has already written win over
        # anything passed on the command line only where the flag is absent.
        stored = orchestration.read_resolutions(args.root, args.feature)
        stored.update(resolutions)
        resolutions = stored

        try:
            bundle = engine.load(config, args.root)
            brief = json.dumps({name: [r.get("id") for r in recs]
                                for name, recs in bundle.items()})[:4000]
        except Exception:
            brief = ""

        report = orchestration.Orchestrator(
            runner, brief=brief, resolutions=resolutions,
            max_repair=args.max_repair, extra_lens=extra_lens,
            clean=not args.no_clean,
            on_phase=lambda phase: print(f"── {phase}", file=sys.stderr),
        ).run(args.feature)

        if report.status == "blocked":
            path = orchestration.write_questions(
                args.root, args.feature, report.disambiguation)
            print(f"\nHuman gate: {len(report.disambiguation)} open question(s).",
                  file=sys.stderr)
            print(f"Answer them in {path}, then run this again.", file=sys.stderr)

        saved = orchestration.save_report(args.root, report)
        print(f"── run saved to {saved}", file=sys.stderr)

        text = report.render()
        if args.output:
            out = pathlib.Path(args.root) / args.output
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {out}")
        else:
            sys.stdout.write(text)

        # blocked and refuted are both non-zero: the line did not propose a change.
        return 0 if report.status == "proposed" else 1

    if args.cmd == "evidence":
        if args.verify:
            path = pathlib.Path(args.root) / args.verify
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                print(f"cannot read {path}: {exc}", file=sys.stderr)
                return 2
            problems = evidence.verify(record, args.root)
            if problems:
                print(f"EVIDENCE DOES NOT MATCH THIS TREE — {len(problems)} problem(s)\n")
                for problem in problems:
                    print(f"  {problem}")
                return 1
            made = record.get("generated_at", "?")
            print(f"evidence verified: every digest still matches (recorded {made})")
            return 0

        record = evidence.build_record(config, args.root, registry)
        text = evidence.render(record)
        if args.output:
            out = pathlib.Path(args.root) / args.output
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {out}")
        else:
            sys.stdout.write(text)
        # Same gating semantics as validate: an evidence record of a failing run is
        # still worth having, but CI must not go green because you asked for one.
        return 1 if record["result"] == "fail" else 0

    report = engine.validate(config, args.root, registry)
    counts = {name: len(recs) for name, recs in engine.load(config, args.root).items()}

    if getattr(args, "as_json", False):
        # Diagnostics are an API. Making a consumer regex the prose to find a code
        # defeats the point of having stable codes at all.
        json.dump(
            {
                "schema": "keelspec-report/1",
                "result": "pass" if report.ok else "fail",
                "counts": counts,
                "errors": len(report.errors),
                "warnings": len(report.warnings),
                "findings": [
                    {
                        "code": d.code,
                        "severity": d.severity,
                        "where": d.where,
                        "message": d.message,
                    }
                    for d in report.diagnostics
                ],
            },
            sys.stdout, indent=2, ensure_ascii=False, sort_keys=True,
        )
        sys.stdout.write("\n")
        return 1 if report.errors else 0

    for w in report.warnings:
        print(f"WARN  {w.render()}")
    for e in report.errors:
        print(f"ERROR {e.render()}")
    summary = ", ".join(f"{n} {c}" for n, c in counts.items())
    print(
        f"\nkeelspec: {summary} — "
        f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)."
    )
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
