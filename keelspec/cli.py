"""The ``keelspec`` command line: build | validate.

    keelspec build                       # regenerate the JSON bundle
    keelspec validate                    # schema + graph + staleness (CI gate)
    keelspec validate --watch            # the same gate, on every save
    keelspec evidence -o build/ev.json   # content-addressed audit record
    keelspec runs                        # what the agent-built line has been doing
    keelspec simulate                    # replay agent scenarios offline
    keelspec tools check                 # MCP servers vs their TOOL- artifacts (PAC-073)
    keelspec lsp                         # language server, on stdio
    keelspec mcp                         # the graph as tools, for an agent
    keelspec -c product.config.yaml -p product_hooks.py validate

Exit code is non-zero iff validation found errors — wire ``keelspec validate`` into CI.
"""
from __future__ import annotations

import argparse
import contextlib
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

    pol = sub.add_parser("policy", help="the governed-agent policy engine")
    pol_sub = pol.add_subparsers(dest="policy_cmd", required=True)
    exp = pol_sub.add_parser(
        "explain", help="decide a hypothetical tool call without executing anything")
    exp.add_argument("agent", help="the agent id, e.g. AGENT-payment-exceptions")
    exp.add_argument("tool", help="the tool id, e.g. TOOL-case-management")
    exp.add_argument("operation", help="the tool operation, e.g. release_funds")
    exp.add_argument("args", nargs="?", default="{}",
                     help="the call's arguments as JSON (default: {})")

    run = sub.add_parser("run", help="run a governed agent (needs keelspec[runtime])")
    run.add_argument("agent", nargs="?", default=None, help="the agent id, e.g. AGENT-x")
    run.add_argument("input", nargs="?", default=None, help="the input text for the run")
    run.add_argument("--resume", default=None, metavar="RUN_ID",
                     help="continue a run paused for approval, once it is approved")
    run.add_argument("--fixtures", default=None, metavar="SCN_ID",
                     help="answer tool calls from this scenario's fixtures (offline)")
    run.add_argument("--capture-content", action="store_true",
                     help="also write prompts, completions and tool data to content.jsonl")
    run.add_argument("--router-explain", action="store_true",
                     help="print the router's plan for the first step before running")
    run.add_argument("--runtime-config", default="keelspec.runtime.yaml",
                     help="router and telemetry settings (default: keelspec.runtime.yaml)")

    tl = sub.add_parser("tools", help="check MCP servers against their TOOL- artifacts, "
                                      "or scaffold a server")
    tl.add_argument("action", choices=["check", "scaffold"])
    tl.add_argument("tool_ids", nargs="*", metavar="TOOL_ID",
                    help="check: these tools (default: all); scaffold: exactly one")
    tl.add_argument("--out", default="servers",
                    help="scaffold: directory the server package goes under (default: servers)")
    tl.add_argument("--force", action="store_true", help="scaffold: overwrite existing files")
    tl.add_argument("--json", action="store_true", dest="as_json",
                    help="check: emit findings as JSON")

    sim = sub.add_parser("simulate", help="replay scenarios offline with a scripted model")
    sim.add_argument("target", nargs="?", default=None,
                     help="an agent (AGENT-x) or one scenario (SCN-y); default: every scenario")
    sim.add_argument("--junit", default=None, metavar="PATH", help="also write JUnit XML here")
    sim.add_argument("--evidence", nargs="?", const="", default=None, metavar="PATH",
                     help="also write an evidence record with the results (default: "
                          ".keelspec/evidence/simulation-<time>.json)")

    srv = sub.add_parser("serve", help="serve governed agents over HTTP, or as MCP tools "
                                       "(needs keelspec[runtime])")
    srv.add_argument("--host", default="127.0.0.1", help="interface (default: 127.0.0.1)")
    srv.add_argument("--port", type=int, default=8080, help="port (default: 8080)")
    srv.add_argument("--mcp", action="store_true",
                     help="serve each deployed agent as an MCP tool on stdio instead")
    srv.add_argument("--any-status", action="store_true",
                     help="serve agents that are not status: deployed (demos only)")
    srv.add_argument("--fixtures", default=None, metavar="SCN_ID",
                     help="answer tool calls from this scenario's fixtures (offline demo)")
    srv.add_argument("--runtime-config", default="keelspec.runtime.yaml",
                     help="router and telemetry settings (default: keelspec.runtime.yaml)")

    apr = sub.add_parser("approvals", help="list, show and sign approval requests")
    apr.add_argument("action", choices=["list", "show", "approve"])
    apr.add_argument("run_id", nargs="?", default=None)
    apr.add_argument("step", nargs="?", type=int, default=None)
    apr.add_argument("--by", default="", help="who approves (recorded in the file)")

    runs = sub.add_parser(
        "runs", help="add up the orchestrator runs, or list/show agent run records")
    runs.add_argument("action", nargs="?", choices=["list", "show"], default=None,
                      help="list agent run records, or show one (default: the line summary)")
    runs.add_argument("run_id", nargs="?", default=None)
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


def _with_telemetry(handler, *args) -> int:
    """Export spans while a runtime command runs, when the OTEL_* environment asks
    for it, and flush them before exiting."""
    from .runtime.telemetry import configure_from_env
    configured = configure_from_env()
    try:
        return handler(*args)
    finally:
        if configured is not None:
            configured.shutdown()


def _run_agent(args, config, registry) -> int:
    from .runtime.bundle import BundleRefused, load_bundle
    from .runtime.fixtures import FixtureExecutor
    from .runtime.router_client import RuntimeSettings

    if bool(args.resume) == bool(args.agent):
        print("give an agent and input, or --resume RUN_ID", file=sys.stderr)
        return 2
    if args.agent and args.input is None:
        print("give the input text for the run", file=sys.stderr)
        return 2
    try:
        bundle, provenance = load_bundle(config, args.root, args.config, registry)
    except BundleRefused as exc:
        print(str(exc), file=sys.stderr)
        return 1
    settings = RuntimeSettings.load(pathlib.Path(args.root) / args.runtime_config)
    if settings.router.problem():
        print(settings.router.problem(), file=sys.stderr)
        return 2
    if args.capture_content:
        settings.capture_content = True
    if args.fixtures:
        try:
            executor = FixtureExecutor.from_scenario(bundle, args.fixtures)
        except KeyError as exc:
            print(str(exc).strip("'\""), file=sys.stderr)
            return 2
    else:
        try:
            import mcp  # noqa: F401  (fail early, with the install hint)

            from .runtime.mcp_client import MCPExecutor
        except ImportError:
            print("running against tool servers needs the runtime extra:\n\n"
                  "    pip install 'keelspec[runtime]'\n\nor run offline with "
                  "--fixtures SCN-id", file=sys.stderr)
            return 2
        executor = MCPExecutor(args.root)
    with contextlib.ExitStack() as stack:
        if hasattr(executor, "close"):
            stack.callback(executor.close)
        return _run_with(args, config, bundle, provenance, settings, executor)


def _run_with(args, config, bundle, provenance, settings, executor) -> int:
    from .runtime import approvals as _ap
    from .runtime.agent import ApprovalPending, resume_agent, run_agent, system_prompt
    from .runtime.fixtures import ToolError
    from .runtime.policy import AgentPolicies
    from .runtime.router_client import RouterClient, new_traceparent

    if args.agent and hasattr(executor, "open"):
        # Open every declared tool's session first: a drifted server refuses the run
        # before the model sees anything (PAC-073).
        try:
            ap = AgentPolicies.from_bundle(bundle, args.agent)
            for tool in ap.tools.values():
                executor.open(tool)
        except KeyError as exc:
            print(str(exc).strip("'\""), file=sys.stderr)
            return 1
        except ToolError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    router = RouterClient(settings.router)
    kw = {"root": args.root, "router": router, "executor": executor, "settings": settings,
          "prices": config.prices}
    try:
        if args.resume:
            result = resume_agent(bundle, provenance, args.resume, **kw)
        else:
            if args.router_explain:
                from .runtime.agent import offered_tools
                ap = AgentPolicies.from_bundle(bundle, args.agent)
                plan = router.explain(
                    [{"role": "system", "content": system_prompt(bundle, ap.agent)},
                     {"role": "user", "content": args.input}], offered_tools(ap),
                    concept=ap.agent.get("concept") or "general.assist", session="explain",
                    critical=ap.agent.get("criticality") == "high",
                    traceparent=new_traceparent())
                print(json.dumps(plan, indent=2), file=sys.stderr)
            result = run_agent(bundle, provenance, args.agent, args.input, **kw)
    except (KeyError, ApprovalPending) as exc:
        print(str(exc).strip("'\""), file=sys.stderr)
        return 1
    rec = result.record
    print(f"── run {rec.run_id}: {rec.outcome} ({len(rec.steps)} step(s))", file=sys.stderr)
    if rec.outcome == "awaiting_approval":
        for req in (_ap.read(args.root, rec.run_id) or {}).get("requests", []):
            if req["status"] == "pending":
                print(f"── approval needed for {req['tool_id']}.{req['operation']} by "
                      f"{', '.join(req['approvers']) or 'a person'}: keelspec approvals "
                      f"approve {rec.run_id} {req['step']} --by NAME, then "
                      f"keelspec run --resume {rec.run_id}", file=sys.stderr)
    if result.final_answer:
        print(result.final_answer)
    return 0 if rec.outcome == "completed" else 1


def _serve(args, config, registry) -> int:
    import os

    from .runtime.bundle import BundleRefused, load_bundle
    from .runtime.fixtures import FixtureExecutor
    from .runtime.router_client import RouterClient, RuntimeSettings
    from .runtime.serve import App, ServeRefused, build_mcp_server, make_server
    try:
        bundle, provenance = load_bundle(config, args.root, args.config, registry)
    except BundleRefused as exc:
        print(str(exc), file=sys.stderr)
        return 1
    report = engine.validate(config, args.root, registry)
    settings = RuntimeSettings.load(pathlib.Path(args.root) / args.runtime_config)
    if settings.router.problem():
        print(settings.router.problem(), file=sys.stderr)
        return 2
    if args.fixtures:
        try:
            FixtureExecutor.from_scenario(bundle, args.fixtures)
        except KeyError as exc:
            print(str(exc).strip("'\""), file=sys.stderr)
            return 2

        def executor_factory():
            return FixtureExecutor.from_scenario(bundle, args.fixtures)
    else:
        try:
            import mcp  # noqa: F401

            from .runtime.mcp_client import MCPExecutor
        except ImportError:
            print("serving against tool servers needs the runtime extra:\n\n"
                  "    pip install 'keelspec[runtime]'\n\nor serve offline with "
                  "--fixtures SCN-id", file=sys.stderr)
            return 2

        def executor_factory():
            return MCPExecutor(args.root)
    try:
        app = App(root=pathlib.Path(args.root), bundle=bundle, provenance=provenance,
                  validation={"ok": report.ok, "errors": len(report.errors),
                              "warnings": len(report.warnings)},
                  settings=settings, router_factory=lambda: RouterClient(settings.router),
                  executor_factory=executor_factory, prices=config.prices,
                  run_token=os.environ.get("KEELSPEC_SERVE_TOKEN") or None,
                  approve_token=os.environ.get("KEELSPEC_APPROVER_TOKEN") or None,
                  any_status=args.any_status)
        if not app.servable():
            print("no agent has status: deployed, so there is nothing to serve "
                  "(--any-status serves them anyway, for a demo)", file=sys.stderr)
            return 1
        if args.mcp:
            build_mcp_server(app).run()
            return 0
        server = make_server(app, args.host, args.port)
    except (ServeRefused, ImportError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    host, port = server.server_address[:2]
    print(f"── serving {', '.join(sorted(app.servable()))} on http://{host}:{port} "
          f"(bundle {provenance.get('bundle_sha256', '')[:12]})", file=sys.stderr)
    if not app.approve_token:
        print("── approvals over HTTP are off (no KEELSPEC_APPROVER_TOKEN); sign with "
              "keelspec approvals approve", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _tool_records(args, config) -> dict[str, dict] | None:
    if "agents" not in config.presets:
        print("product.config.yaml does not enable `presets: [agents]`; there are no "
              "TOOL- artifacts", file=sys.stderr)
        return None
    return {r["id"]: r for r in engine.load(config, args.root).get("tools", []) if r.get("id")}


def _tools(args, config) -> int:
    tools = _tool_records(args, config)
    if tools is None:
        return 2
    unknown = [t for t in args.tool_ids if t not in tools]
    if unknown:
        print(f"no tool {', '.join(unknown)} (known: {', '.join(sorted(tools)) or 'none'})",
              file=sys.stderr)
        return 2

    if args.action == "scaffold":
        from .runtime.scaffold import scaffold
        if len(args.tool_ids) != 1:
            print("tools scaffold takes exactly one TOOL id", file=sys.stderr)
            return 2
        try:
            written = scaffold(tools[args.tool_ids[0]], args.root, args.out, args.force)
        except FileExistsError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        for path in written:
            print(f"wrote {path}")
        return 0

    try:
        import mcp  # noqa: F401

        from .runtime.mcp_client import MCPExecutor, drift
    except ImportError:
        print("tools check connects to MCP servers and needs the runtime extra:\n\n"
              "    pip install 'keelspec[runtime]'\n", file=sys.stderr)
        return 2
    from .diagnostics import Report
    from .runtime.fixtures import ToolError
    report, unreachable = Report(), []
    with MCPExecutor(args.root) as ex:
        for tool_id in args.tool_ids or sorted(tools):
            tool = tools[tool_id]
            try:
                names = ex.tool_names(tool)
            except ToolError as exc:
                unreachable.append(str(exc))
                continue
            for problem in drift(tool, names):
                report.add("PAC-073", problem, tool.get("_file", ""), field="operations")
    if args.as_json:
        json.dump({"findings": [{"code": d.code, "where": d.where, "message": d.message}
                                for d in report.diagnostics],
                   "unreachable": unreachable}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for d in report.diagnostics:
            print(d.render())
        for line in unreachable:
            print(f"cannot check: {line}")
        checked = len(args.tool_ids or tools) - len(unreachable)
        print(f"keelspec tools: {checked} server(s) checked, {len(report.diagnostics)} "
              f"PAC-073 finding(s), {len(unreachable)} unreachable", file=sys.stderr)
    return 1 if report.diagnostics or unreachable else 0


def _simulate(args, config, registry) -> int:
    from datetime import datetime, timezone

    from .runtime import simulate as sim
    from .runtime.bundle import BundleRefused, load_bundle
    try:
        bundle, provenance = load_bundle(config, args.root, args.config, registry,
                                         ignore=("PAC-076",))
    except BundleRefused as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        results = sim.simulate(bundle, provenance, args.target)
    except KeyError as exc:
        print(str(exc).strip("'\""), file=sys.stderr)
        return 2
    for r in results:
        print(f"{'PASS' if r.passed else 'FAIL'}  {r.scenario_id}  ({r.agent_id}, "
              f"{r.outcome}, {r.steps} step(s))")
        for failure in r.failures:
            print(f"      {failure}")
        for note in r.notes:
            print(f"      note: {note}")
    passed = sum(r.passed for r in results)
    print(f"keelspec simulate: {passed}/{len(results)} scenario(s) passed "
          f"(model: {sim.SCRIPTED_MODEL})", file=sys.stderr)
    if args.junit:
        out = pathlib.Path(args.root) / args.junit
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(sim.junit(results), encoding="utf-8", newline="\n")
        print(f"wrote {out}", file=sys.stderr)
    if args.evidence is not None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rel = args.evidence or f".keelspec/evidence/simulation-{stamp}.json"
        record = evidence.build_record(config, args.root, registry,
                                       simulation=sim.evidence_section(results, args.root,
                                                                       provenance))
        out = pathlib.Path(args.root) / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(evidence.render(record), encoding="utf-8", newline="\n")
        print(f"wrote {out}", file=sys.stderr)
    return 0 if passed == len(results) else 1


def _approvals(args) -> int:
    from .runtime import approvals
    if args.action == "list":
        for r in approvals.all_requests(args.root):
            who = f" by {r['approved_by']}" if r["approved_by"] else ""
            print(f"{r['run_id']}  step {r['step']}  {r['tool_id']}.{r['operation']}  "
                  f"{r['status']}{who}")
        return 0
    if not args.run_id:
        print(f"approvals {args.action} needs a run id", file=sys.stderr)
        return 2
    if args.action == "show":
        data = approvals.read(args.root, args.run_id)
        if data is None:
            print(f"no approval requests for run {args.run_id}", file=sys.stderr)
            return 1
        sys.stdout.write(json.dumps(data, indent=2) + "\n")
        return 0
    if args.step is None:
        print("approvals approve needs a step number", file=sys.stderr)
        return 2
    try:
        req = approvals.approve(args.root, args.run_id, args.step, args.by)
    except (KeyError, ValueError) as exc:
        print(str(exc).strip("'\""), file=sys.stderr)
        return 1
    print(f"approved {req['tool_id']}.{req['operation']} at step {req['step']} as "
          f"{req['approved_by']}; now: keelspec run --resume {args.run_id}")
    return 0


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
        extra_vendor = ""
        if args.cross_provider:
            from .runners import CrossProviderLens
            lens = CrossProviderLens()
            extra_vendor = lens.model.split("/", 1)[0]
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
        assessment = risk.assess_artifact(config, bundle, args.feature)
        options = assessment.orchestrator_options()
        if assessment.tier is not None and assessment.tier.independent_critic                 and not args.dry_run:
            # Native critics run on Claude (anthropic); the built-in builder does too.
            builder_vendor = builder.vendor if builder is not None else "anthropic"
            critic_vendors = {"anthropic"} | ({extra_vendor} if extra_lens else set())
            if not critic_vendors - {builder_vendor}:
                print(f"risk tier '{assessment.tier.name}' requires a critic outside the "
                      f"builder's vendor ({builder_vendor}). Add --cross-provider with "
                      "OPENROUTER_API_KEY, or use a builder from another vendor.",
                      file=sys.stderr)
                return 2
        if args.no_clean:
            options["clean"] = False
        if args.max_repair is not None:
            options["max_repair"] = args.max_repair
        if options["risk"].get("tier"):
            print(f"── risk tier: {options['risk']['tier']} "
                  f"(score {options['risk']['score']})", file=sys.stderr)

        agent_hooks: dict = {}
        if "agents" in config.presets and any(
                a.get("id") == args.feature for a in bundle.get("agents", [])):
            # A governed agent: ST-04c scaffolds missing tool servers (only with
            # --write, never on a dry run) and the policy lens joins Verify. Both read
            # the tree as it is when they run, after Develop.
            from .runtime.policy_lens import policy_lens
            from .runtime.scaffold import tool_gaps
            write_servers = args.write and not args.dry_run
            agent_hooks = {
                "deterministic_lenses": {"policy": lambda: policy_lens(
                    engine.load(config, args.root), args.feature)},
                "tools_station": lambda: tool_gaps(
                    engine.load(config, args.root), args.feature, args.root,
                    write=write_servers),
            }
            print("── governed agent: ST-04c Tools and the policy lens join the line",
                  file=sys.stderr)

        try:
            orchestrator = orchestration.Orchestrator(
                runner, brief=brief, resolutions=resolutions,
                extra_lens=extra_lens, approvals=list(approvals.values()),
                on_phase=lambda phase: print(f"── {phase}", file=sys.stderr),
                **options, **agent_hooks,
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

    if args.cmd == "policy":
        from .runtime.policy import explain
        try:
            call_args = json.loads(args.args)
        except ValueError as exc:
            print(f"args must be a JSON object: {exc}", file=sys.stderr)
            return 2
        try:
            out = explain(engine.load(config, args.root), args.agent, args.tool,
                          args.operation, call_args)
        except KeyError as exc:
            print(str(exc).strip("'\""), file=sys.stderr)
            return 2
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        return 0

    if args.cmd == "intake":
        return _intake(args, config)

    if args.cmd == "run":
        return _with_telemetry(_run_agent, args, config, registry)

    if args.cmd == "approvals":
        return _approvals(args)

    if args.cmd == "tools":
        return _tools(args, config)

    if args.cmd == "serve":
        return _with_telemetry(_serve, args, config, registry)

    if args.cmd == "simulate":
        return _with_telemetry(_simulate, args, config, registry)

    if args.cmd == "runs" and args.action:
        from .runtime import records
        if args.action == "list":
            for r in records.list_runs(args.root):
                print(f"{r.run_id}  {r.agent_id}  {r.outcome}  {r.started_at}  "
                      f"{len(r.steps)} step(s)")
            return 0
        if not args.run_id:
            print("runs show needs a run id", file=sys.stderr)
            return 2
        try:
            rec = records.read(args.root, args.run_id)
        except (OSError, ValueError) as exc:
            print(f"cannot read run {args.run_id}: {exc}", file=sys.stderr)
            return 1
        sys.stdout.write(json.dumps(rec.to_dict(), indent=2, sort_keys=True) + "\n")
        return 0

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
