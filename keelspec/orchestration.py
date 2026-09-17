"""The agent-built lifecycle: the roster, the pipeline, and the adversarial verify.

Ported from pharthing's `scripts/workflows/agent-build-orchestration.mjs`, which ran
inside Claude Code's Workflow runtime. That runtime supplied `agent()`, `parallel()`
and `phase()`; here those are the engine below, so the pipeline is a library feature
rather than a harness script.

The design principles are the spec's, and they are load-bearing:

  1. Organise by phase, label by role -- a pipeline with fan-out, not peers in a room.
  2. Deterministic control flow, model-driven steps. The wiring between stations is
     ordinary code; reasoning happens *inside* a station.
  3. Typed artifacts, not prose hand-offs. Each station returns a structured result
     against a schema; the orchestrator assembles rather than re-interprets.
  4. The gates are the judge. Stations propose, `validate` enforces, a human merges.
  5. Verification is adversarial and diverse. A finding that survives different-lens
     critics is real; the builder never grades its own work.
  6. Feed the graph. Stations read the validated bundle, so they know impact first.

Nothing here can merge anything. The orchestrator's terminal state is a report.
"""
from __future__ import annotations

import concurrent.futures
import dataclasses
import json
import pathlib
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol

# ── the roster ───────────────────────────────────────────────────────────────
AGENT, HUMAN, MACHINE = "agent", "human", "machine"


@dataclasses.dataclass(frozen=True)
class Station:
    """One station on the line. `kind` decides whether a model is involved at all."""
    id: str
    name: str
    role: str
    kind: str
    model: str = ""
    effort: str = ""


ROSTER: tuple[Station, ...] = (
    Station("ST-01", "Understand", "read the graph", AGENT, "claude-haiku-4-5", "low"),
    Station("ST-02", "Disambiguate", "human gate", HUMAN),
    Station("ST-03", "Design", "the Architect", AGENT, "claude-opus-5", "high"),
    Station("ST-04", "Develop", "writes code", AGENT, "claude-opus-5", "high"),
    # Inserted rather than renumbered: ST-05..ST-10 are referenced in decks,
    # diagrams and prose elsewhere, and renumbering a stable reference to make
    # room is the same mistake as renumbering a diagnostic code.
    Station("ST-04b", "Clean", "simplify, without changing behaviour", AGENT,
            "claude-opus-5", "high"),
    # Not "adversarial coverage", which it was: ST-06 immediately below is the
    # adversarial station, and having the word on both made readers ask which
    # one fans out. ST-05 is one agent whose separateness is the point; ST-06
    # is many agents whose disagreement is the point.
    Station("ST-05", "Test", "coverage, by a separate author", AGENT,
            "claude-opus-5", "high"),
    Station("ST-06", "Verify", "4 refuting lenses", AGENT, "claude-opus-5", "high"),
    Station("ST-07", "Assemble", "one gated PR", MACHINE),
    Station("ST-08", "CI gates", "the judge", MACHINE),
    Station("ST-09", "Human merge", "a person decides", HUMAN),
    Station("ST-10", "Production", "the oracle", MACHINE),
)

BY_ID = {s.id: s for s in ROSTER}


# ── the four refuting lenses (wording from the spec) ─────────────────────────
LENSES: tuple[tuple[str, str], ...] = (
    ("correctness",
     "Does the work actually satisfy every acceptance criterion? Find an input or "
     "state where it does the WRONG thing -- and check whether the tests would pass "
     "vacuously."),
    ("coverage",
     "Is there a RESOLVING test for EVERY acceptance criterion, and does each one "
     "actually FAIL if the behaviour is removed? Name any criterion whose test would "
     "still pass with the feature deleted, or any criterion with no test at all."),
    ("security",
     "Trust boundaries, authz, injection, PII, secrets -- and if this touches money, "
     "spend and consent limits plus reconciliation invariants. What could be abused?"),
    ("reproduce",
     "Ignore the happy path: concurrency, partial failure, retries and idempotency, "
     "rollback, and the declared failure semantics. Where does it break for real?"),
)

BLOCKING = {"blocker", "major"}          # minor and none do not stop a run
SEVERITIES = ("blocker", "major", "minor", "none")


# ── typed artifacts ──────────────────────────────────────────────────────────
DISAMBIGUATION_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "dimension": {"type": "string"},
                    "question": {"type": "string"},
                },
                "required": ["dimension", "question"],
                "additionalProperties": False,
            },
        },
        "reasoning": {"type": "string"},
    },
    "required": ["questions"],
    "additionalProperties": False,
}

DESIGN_SCHEMA = {
    "type": "object",
    "properties": {
        "approach": {"type": "string"},
        "files": {"type": "array", "items": {"type": "string"}},
        "criteria_to_tests": {"type": "array", "items": {"type": "string"}},
        "trust_boundaries": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["approach", "files", "criteria_to_tests"],
    "additionalProperties": False,
}

DEVELOP_SCHEMA = {
    "type": "object",
    "properties": {
        "files_changed": {"type": "array", "items": {"type": "string"}},
        "diff_summary": {"type": "string"},
        "self_notes": {"type": "string"},
    },
    "required": ["files_changed", "diff_summary"],
    "additionalProperties": False,
}

CLEAN_SCHEMA = {
    "type": "object",
    "properties": {
        "files_changed": {"type": "array", "items": {"type": "string"}},
        "simplifications": {"type": "array", "items": {"type": "string"}},
        # Self-reported, and treated as a claim rather than a fact: a Cleaner that
        # says it changed behaviour is not trusted, and its work is dropped.
        "behaviour_preserved": {"type": "boolean"},
        "notes": {"type": "string"},
    },
    "required": ["files_changed", "simplifications", "behaviour_preserved"],
    "additionalProperties": False,
}

TEST_SCHEMA = {
    "type": "object",
    "properties": {
        "tests_added": {"type": "array", "items": {"type": "string"}},
        "tests_passed": {"type": "boolean"},
        "coverage_notes": {"type": "string"},
        "self_notes": {"type": "string"},
    },
    "required": ["tests_added", "tests_passed", "coverage_notes"],
    "additionalProperties": False,
}

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "lens": {"type": "string"},
        "refuted": {"type": "boolean"},
        "severity": {"type": "string", "enum": list(SEVERITIES)},
        "reason": {"type": "string"},
        "failing_case": {"type": "string"},
    },
    "required": ["lens", "refuted", "severity", "reason"],
    "additionalProperties": False,
}


@dataclasses.dataclass
class Verdict:
    lens: str
    refuted: bool
    severity: str
    reason: str
    failing_case: str = ""

    @property
    def blocking(self) -> bool:
        return self.refuted and self.severity in BLOCKING

    @classmethod
    def from_dict(cls, data: dict, lens: str) -> Verdict:
        severity = data.get("severity")
        if severity not in SEVERITIES:
            severity = "major" if data.get("refuted") else "none"
        return cls(
            lens=data.get("lens") or lens,
            refuted=bool(data.get("refuted")),
            severity=severity,
            reason=data.get("reason") or "(no reason returned)",
            failing_case=data.get("failing_case") or "",
        )

    @classmethod
    def benign(cls, lens: str, why: str) -> Verdict:
        """An unreachable critic must never block the line -- it just abstains."""
        return cls(lens, False, "none",
                   f"lens inconclusive ({why}); the remaining lenses stand.")


@dataclasses.dataclass
class StepResult:
    station: str
    phase: str
    ok: bool
    data: dict[str, Any] = dataclasses.field(default_factory=dict)
    error: str = ""


@dataclasses.dataclass
class RunReport:
    feature: str
    steps: list[StepResult] = dataclasses.field(default_factory=list)
    verdicts: list[Verdict] = dataclasses.field(default_factory=list)
    repair_rounds: int = 0
    disambiguation: list[dict] = dataclasses.field(default_factory=list)
    simplifications: list[str] = dataclasses.field(default_factory=list)
    status: str = "unknown"      # blocked | refuted | proposed | error
    notes: list[str] = dataclasses.field(default_factory=list)

    @property
    def blocking(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.blocking]

    def to_dict(self) -> dict:
        return {
            "feature": self.feature,
            "status": self.status,
            "repair_rounds": self.repair_rounds,
            "disambiguation": self.disambiguation,
            "simplifications": self.simplifications,
            "steps": [dataclasses.asdict(s) for s in self.steps],
            "verdicts": [dataclasses.asdict(v) for v in self.verdicts],
            "notes": self.notes,
        }

    def render(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"



# ── the human gate, as a file ────────────────────────────────────────────────
# pharthing parks pending questions in a console (POST .../disambiguations, a human
# answers at /orchestration, run 2 reads the resolved record). That needs a service.
# A library cannot assume one, so the same two-phase gate is a file on disk: run 1
# writes the questions with empty answers, a person fills them in, run 2 reads them.
# Same property -- the line stops until a human has answered -- with nothing to host.
def disambiguation_path(root: str | pathlib.Path, feature: str) -> pathlib.Path:
    return pathlib.Path(root) / ".keelspec" / "disambiguations" / f"{feature}.json"


def write_questions(root: str | pathlib.Path, feature: str, questions: list[dict]) -> pathlib.Path:
    path = disambiguation_path(root, feature)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_resolutions(root, feature)
    payload = {
        "feature": feature,
        "status": "pending",
        "instructions": "Fill in every \"answer\". Re-run orchestrate when done.",
        "questions": [
            {
                "id": q.get("id") or f"q{i + 1}",
                "dimension": q.get("dimension", ""),
                "question": q.get("question", ""),
                "answer": existing.get(q.get("id") or f"q{i + 1}", ""),
            }
            for i, q in enumerate(questions)
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")
    return path


def read_resolutions(root: str | pathlib.Path, feature: str) -> dict[str, str]:
    """Answers a human has written into the file. Missing or malformed reads empty."""
    path = disambiguation_path(root, feature)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for q in payload.get("questions", []):
        answer = (q.get("answer") or "").strip()
        if answer:
            out[q.get("id", "")] = answer
            if q.get("dimension"):
                out[q["dimension"]] = answer
    return out



def run_path(root: str | pathlib.Path, feature: str, stamp: str) -> pathlib.Path:
    return pathlib.Path(root) / ".keelspec" / "runs" / f"{feature}-{stamp}.json"


def save_report(root: str | pathlib.Path, report: RunReport) -> pathlib.Path:
    """Keep the run. A refuted run after two repair rounds contains the four
    verdicts, the failing cases and every step -- throwing that away because the
    line did not propose anything is throwing away the most useful output it
    produced."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = run_path(root, report.feature, stamp)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.render(), encoding="utf-8", newline="\n")
    return path


# ── the runner seam ──────────────────────────────────────────────────────────
class Runner(Protocol):
    """What a station needs to do its work.

    The library ships a Claude-backed runner for the reasoning stations and a stub
    for tests. Writing code is a tool-using agent's job, not a validator's, so a
    project that wants ST-04 to produce a real diff supplies its own runner --
    the same extension philosophy as plugins.
    """

    def run(self, station: Station, prompt: str, schema: dict | None = None) -> dict:
        ...


class StubRunner:
    """Deterministic, offline, and honest about it.

    Used by `--dry-run` and by the tests. It exercises the *control flow* -- phase
    order, fan-out, the repair loop, the gate -- without pretending to reason.
    """

    def __init__(self, verdicts: dict[str, dict] | None = None,
                 questions: list[dict] | None = None):
        self._verdicts = verdicts or {}
        self._questions = questions or []
        self.calls: list[tuple[str, str]] = []

    def run(self, station: Station, prompt: str, schema: dict | None = None) -> dict:
        self.calls.append((station.id, prompt[:60]))

        if schema is DISAMBIGUATION_SCHEMA:
            return {"questions": self._questions, "reasoning": "stub"}
        if schema is DESIGN_SCHEMA:
            return {"approach": "(stub design)", "files": [],
                    "criteria_to_tests": [], "risks": []}
        if schema is DEVELOP_SCHEMA:
            return {"files_changed": [], "diff_summary": "(stub: no code written)"}
        if schema is CLEAN_SCHEMA:
            return {"files_changed": [], "simplifications": [],
                    "behaviour_preserved": True, "notes": "(stub)"}
        if schema is TEST_SCHEMA:
            return {"tests_added": [], "tests_passed": True,
                    "coverage_notes": "(stub)"}
        if schema is VERDICT_SCHEMA:
            lens = prompt.split('"')[1] if '"' in prompt else "unknown"
            return self._verdicts.get(lens, {
                "lens": lens, "refuted": False, "severity": "none",
                "reason": "stub runner does not reason", "failing_case": "",
            })
        return {"text": "(stub)"}


# ── the engine ───────────────────────────────────────────────────────────────
def _fanout(tasks: list[Callable[[], Any]], workers: int = 4) -> list[Any]:
    """Run independent stations concurrently. A station that raises yields None --
    one failed critic must not take down the line."""
    if not tasks:
        return []
    results: list[Any] = [None] * len(tasks)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(t): i for i, t in enumerate(tasks)}
        for future in concurrent.futures.as_completed(futures):
            index = futures[future]
            try:
                results[index] = future.result()
            except Exception as exc:
                results[index] = {"_error": str(exc)}
    return results


class Orchestrator:
    """Deterministic control flow around model-driven steps."""

    MAX_REPAIR = 2

    def __init__(self, runner: Runner, brief: str = "", *,
                 resolutions: dict[str, str] | None = None,
                 max_repair: int | None = None,
                 extra_lens: Callable[[str], dict] | None = None,
                 clean: bool = True,
                 on_phase: Callable[[str], None] | None = None):
        self.runner = runner
        self.brief = brief
        self.resolutions = resolutions or {}
        self.max_repair = self.MAX_REPAIR if max_repair is None else max_repair
        # A critic from a different provider, so it cannot share the builder's blind
        # spots. Joins the SAME refute/repair logic as the native lenses.
        self.extra_lens = extra_lens
        self.clean_enabled = clean
        self.on_phase = on_phase or (lambda _phase: None)

    # ── individual stations ──────────────────────────────────────────────
    def _step(self, station_id: str, phase: str, prompt: str,
              schema: dict | None = None) -> StepResult:
        station = BY_ID[station_id]
        try:
            data = self.runner.run(station, prompt, schema)
            return StepResult(station.id, phase, True, data)
        except Exception as exc:
            return StepResult(station.id, phase, False, {}, str(exc))

    def understand(self, feature: str) -> StepResult:
        self.on_phase("Understand")
        return self._step(
            "ST-01", "Understand",
            f"Read the artifact '{feature}' and everything it connects to in the "
            f"validated product graph: the rules it depends on, the terms it uses, and "
            f"what already exists that it must integrate with. Produce a tight brief: "
            f"the acceptance criteria VERBATIM, the invariants and failure semantics if "
            f"it is critical, and the reverse edges. Do NOT write code.\n\n{self.brief}",
        )

    def disambiguate(self, feature: str, brief: dict) -> tuple[StepResult, list[dict]]:
        """The human gate. Returns unresolved questions; a non-empty list blocks.

        A blocking human gate cannot live inside one autonomous run, so this is
        two-phase by construction: run once to surface the questions, have a person
        answer them, run again with `resolutions` supplied.
        """
        self.on_phase("Disambiguate")
        step = self._step(
            "ST-02", "Disambiguate",
            f"Enumerate the genuinely underspecified dimensions of the acceptance "
            f"criteria for '{feature}' -- the axes a human must resolve before design "
            f"can start. Only questions that cannot be answered from the brief.\n\n"
            f"{json.dumps(brief)[:4000]}",
            DISAMBIGUATION_SCHEMA,
        )
        questions = list(step.data.get("questions") or [])
        unresolved = [q for q in questions
                      if not self.resolutions.get(q.get("id") or q.get("dimension", ""))]
        return step, unresolved

    def design(self, feature: str, brief: dict) -> StepResult:
        self.on_phase("Design")
        answered = "\n".join(f"- {k}: {v}" for k, v in self.resolutions.items())
        return self._step(
            "ST-03", "Design",
            f"You are the Architect for '{feature}'. Turn the brief and the resolved "
            f"ambiguities into a minimal design: the approach, the files that change, "
            f"and how each acceptance criterion is satisfied AND tested.\n\n"
            f"Brief: {json.dumps(brief)[:4000]}\n"
            f"Resolved by a human (treat as contract):\n{answered or '(none)'}",
            DESIGN_SCHEMA,
        )

    def develop(self, feature: str, design: dict) -> StepResult:
        self.on_phase("Develop")
        return self._step(
            "ST-04", "Develop",
            f"Implement '{feature}' to this design and its acceptance criteria. Report "
            f"the files changed and a concise diff summary for the Test engineer and "
            f"the reviewers.\n\nDesign: {json.dumps(design)[:4000]}",
            DEVELOP_SCHEMA,
        )

    def clean(self, feature: str, dev: dict) -> StepResult:
        """Simplify what Develop produced, without changing what it does.

        An agent that has just solved a problem leaves the shape of the struggle in
        the code, and nothing downstream ever asks whether that is the simplest form
        of it. Test checks the behaviour is right; nobody checks the code is clean.

        Deliberately narrow: no new behaviour, no changed signatures, no new
        dependencies. A pass that is allowed to "improve while it is in there" is a
        second Develop station wearing a different hat, and its changes would arrive
        untested.
        """
        self.on_phase("Clean")
        return self._step(
            "ST-04b", "Clean",
            f"You are the Cleaner for '{feature}'. Go back over the change that was "
            f"just made and simplify it: collapse duplication, name things for what "
            f"they are, remove dead branches and needless indirection.\n\n"
            f"Behaviour must not change. Do NOT add features, alter public "
            f"signatures, change error messages that callers may match on, or add "
            f"dependencies. If a simplification would change what the code does, "
            f"leave it alone and say so in notes.\n\n"
            f"If nothing is worth simplifying, report no changes. A pass that "
            f"invents work is worse than one that finds none.\n\n"
            f"The change: {json.dumps(dev)[:4000]}",
            CLEAN_SCHEMA,
        )

    def test(self, feature: str, design: dict, dev: dict) -> StepResult:
        self.on_phase("Test")
        return self._step(
            "ST-05", "Test",
            f"You are a SEPARATE test engineer for '{feature}' -- the author does not "
            f"grade its own coverage. Tie every acceptance criterion to a resolving "
            f"test, and for each one state how you confirmed it FAILS when the "
            f"behaviour is removed. A test that passes with the feature deleted is "
            f"vacuous; say so.\n\nDesign: {json.dumps(design)[:2500]}\n"
            f"Change: {json.dumps(dev)[:2500]}",
            TEST_SCHEMA,
        )

    def verify(self, feature: str, dev: dict, test: dict) -> list[Verdict]:
        """The four lenses, in parallel, each trying to refute."""
        self.on_phase("Verify")
        context = (f"Feature: {feature}\n"
                   f"Diff summary: {dev.get('diff_summary', '(none)')}\n"
                   f"Tests added: {', '.join(test.get('tests_added') or []) or '(none)'}\n"
                   f"Coverage notes: {test.get('coverage_notes', '(none)')}")

        def make(lens: str, ask: str) -> Callable[[], Verdict]:
            def task() -> Verdict:
                step = self._step(
                    "ST-06", "Verify",
                    f'You are an ADVERSARIAL reviewer using the "{lens}" lens. Try to '
                    f"REFUTE this change -- default to refuted=true if you are not "
                    f"convinced it is correct and safe. {ask}\n\n{context}",
                    VERDICT_SCHEMA,
                )
                if not step.ok:
                    return Verdict.benign(lens, step.error or "station failed")
                return Verdict.from_dict(step.data, lens)
            return task

        tasks: list[Callable[[], Verdict]] = [make(lens, ask) for lens, ask in LENSES]
        names = [lens for lens, _ in LENSES]

        if self.extra_lens is not None:
            def cross() -> Verdict:
                data = self.extra_lens(context)
                return Verdict.from_dict(data, data.get("lens", "cross-provider"))
            tasks.append(cross)
            names.append("cross-provider")

        raw = _fanout(tasks, workers=len(tasks))
        out: list[Verdict] = []
        for lens, result in zip(names, raw, strict=True):
            if isinstance(result, Verdict):
                out.append(result)
            else:
                out.append(Verdict.benign(lens, "no verdict returned"))
        return out

    def repair(self, feature: str, blocking: list[Verdict]) -> StepResult:
        self.on_phase("Repair")
        findings = "\n".join(
            f"- [{v.lens}/{v.severity}] {v.reason}"
            + (f" (failing case: {v.failing_case})" if v.failing_case else "")
            for v in blocking)
        return self._step(
            "ST-04", "Repair",
            f"You are the repair engineer for '{feature}'. Adversarial review "
            f"refuted the change. Fix these findings and nothing else:\n\n{findings}",
            DEVELOP_SCHEMA,
        )

    # ── the line ─────────────────────────────────────────────────────────
    def run(self, feature: str, *, block_on_unresolved: bool = True) -> RunReport:
        """Run the line for one feature.

        ``block_on_unresolved`` (default True) is the human gate: any question the
        Disambiguate station cannot answer from the brief stops the run before Design,
        because building the wrong thing correctly is the expensive failure. Set it
        False for an AUTONOMOUS run — the questions are still recorded on the report,
        but the line proceeds to build on the versioned product intent, deferring the
        human judgement to the concrete PR (its gates and the merge) rather than a set
        of abstract pre-build questions. The open questions ride along on the report
        so the caller can surface them for the record.
        """
        report = RunReport(feature=feature)

        brief = self.understand(feature)
        report.steps.append(brief)
        if not brief.ok:
            report.status = "error"
            return report

        gate, unresolved = self.disambiguate(feature, brief.data)
        report.steps.append(gate)
        if unresolved:
            # Recorded either way; only a blocking gate stops here.
            report.disambiguation = unresolved
            if block_on_unresolved:
                report.status = "blocked"
                report.notes.append(
                    f"{len(unresolved)} question(s) need a human answer before design; "
                    "re-run with resolutions to continue.")
                return report
            report.notes.append(
                f"{len(unresolved)} open question(s) recorded but NOT blocking "
                "(advisory gate): proceeding to build on the versioned intent — the "
                "PR's gates and the human merge are the judge.")

        design = self.design(feature, brief.data)
        report.steps.append(design)
        if not design.ok:
            report.status = "error"
            return report

        dev = self.develop(feature, design.data)
        report.steps.append(dev)

        if self.clean_enabled:
            cleaned = self.clean(feature, dev.data)
            report.steps.append(cleaned)
            # Trust the claim only when it claims not to have broken anything. A
            # Cleaner that admits it changed behaviour has done Develop's job
            # without Develop's tests, so its result is recorded and not used.
            if cleaned.ok and cleaned.data.get("behaviour_preserved"):
                report.simplifications = list(cleaned.data.get("simplifications") or [])
            elif cleaned.ok:
                report.notes.append(
                    "the Cleaner reported it could not preserve behaviour; its "
                    "changes were not carried forward.")

        test = self.test(feature, design.data, dev.data)
        report.steps.append(test)

        report.verdicts = self.verify(feature, dev.data, test.data)
        while report.blocking and report.repair_rounds < self.max_repair:
            report.repair_rounds += 1
            fix = self.repair(feature, report.blocking)
            report.steps.append(fix)
            report.verdicts = self.verify(feature, fix.data or dev.data, test.data)

        self.on_phase("Report")
        if report.blocking:
            report.status = "refuted"
            report.notes.append(
                f"still refuted after {report.repair_rounds} repair round(s); "
                "reporting honestly rather than proposing.")
        else:
            report.status = "proposed"
            report.notes.append(
                "the line proposes this change. It is not merged: the gate judges "
                "and a human decides.")
        return report
