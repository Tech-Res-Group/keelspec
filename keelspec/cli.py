"""The ``keelspec`` command line: build | validate.

    keelspec build                       # regenerate the JSON bundle
    keelspec validate                    # schema + graph + staleness (CI gate)
    keelspec validate --watch            # the same gate, on every save
    keelspec evidence -o build/ev.json   # content-addressed audit record
    keelspec runs                        # what the agent-built line has been doing
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

from . import engine, evidence, metrics, orchestration, risk
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
    orc.add_argument("--approve", action="append", default=[], metavar="ROLE=NAME",
                     help="accept the spec at the human gate in a role (repeatable)")
    orc.add_argument("--max-repair", type=int, default=None,
                     help=f"bounded repair rounds (default {orchestration.Orchestrator.MAX_REPAIR})")
    orc.add_argument("--write", action="store_true",
                     help="let the Develop station actually edit files (default: propose only)")
    orc.add_argument("--builder", choices=["keelspec", "claude-code", "codex"],
                     default="keelspec",
                     help="who runs ST-04 Develop: the built-in station (default), or an "
                          "external agent's CLI in an isolated git worktree")
    orc.add_argument("--no-clean", action="store_true",
                     help="skip ST-04b Clean (one fewer model call per run)")
    orc.add_argument("--cross-provider", action="store_true",
                     help="add a non-Claude critic via OpenRouter (needs OPENROUTER_API_KEY)")
    orc.add_argument("-o", "--output", default=None,
                     help="write the run report here instead of stdout")

    ink = sub.add_parser(
        "intake",
        help="import a ticket as a draft feature, or sync imported features with their tickets",
    )
    ink.add_argument("ticket", nargs="?", default=None,
                     help="a GitHub issue URL, owner/repo#N, a Jira URL or a Jira key")
    ink.add_argument("--id", default=None, dest="feature_id",
                     help="the feature id to create (default: derived from the ticket key)")
    ink.add_argument("--sync", action="store_true",
                     help="check every imported feature against its ticket and show the changes")
    ink.add_argument("--apply", action="store_true",
                     help="with --sync, write the changes (refused on the default branch)")

    runs = sub.add_parser("runs", help="add up the orchestrator runs kept in .keelspec/runs")
    runs.add_argument("--json", action="store_true", dest="as_json",
                      help="emit the summary as JSON")
    runs.add_argument("--evidence", default=None, metavar="DIR",
                      help="kept evidence records, for the spec-drift rate "
                           "(default: .keelspec/evidence)")
    return p


def _pairs(values: list[str], flag: str, shape: str) -> dict[str, str] | None:
    out = {}
    for pair in values:
        key, _, value = pair.partition("=")
        if not key.strip() or not value.strip():
            print(f"{flag} expects {shape}, got: {pair}", file=sys.stderr)
            return None
        out[key.strip()] = value.strip()
    return out


def _brief(config, bundle: dict, feature: str) -> str:
    """The feature, what it points at, and what points at it -- then the rest by id.

    A brief of ids alone gives every station the names of the rules without their
    text, which is how a change ends up satisfying its criteria and breaking the
    rule next door.
    """
    def clean(rec: dict) -> dict:
        return {k: v for k, v in rec.items() if k != "_file" and v not in (None, "", [])}

    record = risk.find(bundle, feature)
    linked: list[dict] = []
    if record is not None:
        wanted: set[str] = set()
        for t in config.types:
            for ref in t.references:
                for rec in bundle.get(t.name, []):
                    raw = rec.get(ref.field)
                    vals = raw if isinstance(raw, list) else [raw] if raw else []
                    if rec.get("id") == feature:
                        wanted.update(str(v) for v in vals)
                    elif feature in vals:
                        wanted.add(rec.get("id"))
        linked = [clean(r) for recs in bundle.values() if isinstance(recs, list)
                  for r in recs if isinstance(r, dict) and r.get("id") in wanted]
    payload = {
        "artifact": clean(record) if record else None,
        "linked": linked,
        "graph": {name: [r.get("id") for r in recs]
                  for name, recs in bundle.items() if isinstance(recs, list)},
    }
    return json.dumps(payload, default=str)[:6000]


def _intake(args, config) -> int:
    import difflib

    from . import intake

    if args.sync == bool(args.ticket):
        print("give a ticket to import, or --sync, not both", file=sys.stderr)
        return 2
    try:
        if args.ticket:
            plan = intake.plan_import(config, args.root, intake.fetch(args.ticket),
                                      args.feature_id)
            if plan.action == "error":
                print(plan.error, file=sys.stderr)
                return 1
            intake.apply(args.root, plan)
            print(f"wrote {plan.path} (status: draft; review it, then commit it with "
                  f"{intake.state_path(args.root, plan.feature)})")
            return 0

        if args.apply and intake.on_default_branch(args.root):
            print("refusing to --apply on the default branch: sync changes are proposals. "
                  "Switch to a branch, apply, commit, and open a pull request.", file=sys.stderr)
            return 2
        status = 0
        for feature in intake.tracked(args.root):
            plan = intake.plan_sync(config, args.root, feature)
            if plan.action == "unchanged":
                if args.apply and plan.ticket is not None:
                    intake.apply(args.root, plan)        # record the new revision
                print(f"{feature}: up to date")
            elif plan.action == "error":
                print(f"{feature}: {plan.error}", file=sys.stderr)
                status = 1
            elif plan.action == "conflict":
                print(f"{feature}: CONFLICT in {', '.join(plan.conflicts)}: changed both in "
                      f"{plan.ticket.key} and in the file since the last sync. A person "
                      f"decides; nothing was written.", file=sys.stderr)
                status = 1
            else:
                diff = difflib.unified_diff(
                    plan.old_text.splitlines(keepends=True), plan.new_text.splitlines(keepends=True),
                    fromfile=f"a/{feature}.md", tofile=f"b/{feature}.md")
                sys.stdout.write("".join(diff))
                if args.apply:
                    intake.apply(args.root, plan)
                    print(f"{feature}: updated from {plan.ticket.key}")
                else:
                    print(f"{feature}: {plan.ticket.key} changed (pass --apply on a branch to write it)")
        return status
    except intake.IntakeError as exc:
        print(f"intake: {exc}", file=sys.stderr)
        return 1


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
        resolutions = _pairs(args.resolve, "--resolve", "ID=ANSWER")
        approved = _pairs(args.approve, "--approve", "ROLE=NAME")
        if resolutions is None or approved is None:
            return 2

        builder = None
        if args.dry_run:
            runner = orchestration.StubRunner()
            if args.builder != "keelspec":
                print(f"--dry-run: the {args.builder} builder is not invoked",
                      file=sys.stderr)
        elif args.builder != "keelspec":
            # An external agent builds; every other station is unchanged, so Test,
            # the critics and Triage judge it exactly as they judge the built-in one.
            from .builders import BUILDERS, protected_paths
            from .runners import ClaudeRunner
            builder = BUILDERS[args.builder](
                args.root, fallback=ClaudeRunner(),
                protected=protected_paths(config, config_path=args.config,
                                          plugin=args.plugin))
            runner = builder
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

        approvals = {a["role"]: a for a in
                     orchestration.read_approvals(args.root, args.feature)}
        stamp = orchestration._now()
        approvals.update({role: {"role": role, "by": name, "at": stamp}
                          for role, name in approved.items()})

        try:
            bundle = engine.load(config, args.root)
        except Exception:
            bundle = {}
        brief = _brief(config, bundle, args.feature) if bundle else ""

        # The tier decides lenses, approvers and repair bounds; a flag given on this
        # command line still wins, and the report records the tier either way.
        options = risk.assess_artifact(config, bundle, args.feature).orchestrator_options()
        if args.no_clean:
            options["clean"] = False
        if args.max_repair is not None:
            options["max_repair"] = args.max_repair
        if options["risk"].get("tier"):
            print(f"── risk tier: {options['risk']['tier']} "
                  f"(score {options['risk']['score']})", file=sys.stderr)

        try:
            orchestrator = orchestration.Orchestrator(
                runner, brief=brief, resolutions=resolutions,
                extra_lens=extra_lens, approvals=list(approvals.values()),
                on_phase=lambda phase: print(f"── {phase}", file=sys.stderr),
                **options,
            )
        except ValueError as exc:
            print(f"product.config.yaml delivery policy: {exc}", file=sys.stderr)
            return 2
        try:
            report = orchestrator.run(args.feature)
        except BaseException:
            if builder is not None:
                builder.finish(None)          # never leave a stray worktree behind
            raise

        if builder is not None:
            stamp = orchestration._now().replace("-", "").replace(":", "")
            patch = orchestration.run_path(args.root, args.feature, stamp).with_suffix(".patch")
            try:
                for note in builder.finish(report, write=args.write and
                                           report.status == "proposed", patch_path=patch):
                    report.notes.append(note)
                    print(f"── {note}", file=sys.stderr)
                if args.write and report.status != "proposed" and report.builder.get("patch"):
                    report.notes.append("--write was given, but the line did not propose "
                                        "this change, so it was not applied")
            except Exception as exc:          # applying can fail on a dirty tree
                report.notes.append(f"the {args.builder} change could not be applied: {exc}")
                print(f"── could not apply the change: {exc}", file=sys.stderr)
            if builder.vendor == "anthropic" and extra_lens is None:
                # The native critics run on Claude too. Say so on the record; a
                # tier that needs independence should add --cross-provider.
                report.notes.append(
                    "the builder and every critic share a model vendor (anthropic); "
                    "add --cross-provider for a critic outside the builder's family")

        if report.status == "blocked":
            path = orchestration.write_questions(
                args.root, args.feature, report.questions,
                required_roles=orchestrator.required_approvers)
            if report.disambiguation:
                print(f"\nHuman gate: {len(report.disambiguation)} open question(s).",
                      file=sys.stderr)
            if report.approvals_missing:
                print("Human gate: the spec needs accepting by "
                      + ", ".join(report.approvals_missing) + ".", file=sys.stderr)
            print(f"Complete {path}, then run this again.", file=sys.stderr)

        saved = orchestration.save_report(args.root, report)
        print(f"── run saved to {saved}", file=sys.stderr)
        if report.status == "proposed":
            # The link from this run to the PR that merges it, for cost per merged PR.
            print(f"── when you commit this change, add the trailer:  KeelSpec-Run: {saved.stem}",
                  file=sys.stderr)

        text = report.render()
        if args.output:
            out = pathlib.Path(args.root) / args.output
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {out}")
        else:
            sys.stdout.write(text)

        # blocked, refuted and needs-human are all non-zero: nothing was proposed.
        return 0 if report.status == "proposed" else 1

    if args.cmd == "intake":
        return _intake(args, config)

    if args.cmd == "runs":
        evidence_dir = (pathlib.Path(args.root) / args.evidence if args.evidence
                        else metrics.evidence_dir(args.root))
        summary = metrics.summarise(
            metrics.load_runs(args.root), prices=config.prices,
            merged=metrics.merged_run_ids(args.root),
            evidence=metrics.load_evidence(evidence_dir))
        if args.as_json:
            sys.stdout.write(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        else:
            sys.stdout.write(metrics.render_text(summary))
        return 0

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
