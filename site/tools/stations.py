"""The agent-built lifecycle: the ST-01..ST-10 roster, as the site's hero rail.

The roster, the lens wording and the fan-out come from pharthing's
`docs/decks/build_pdlc_roles_pptx.py` -- the deck is the source of truth for this
model and the site is downstream of it. Where the deck and this file disagree, the
deck wins.

The visual grammar carries the argument, so it is deliberate:

    agent   a face   -- it thinks, and can be wrong
    human   a figure -- a person decides, and autonomy stops here
    machine a plate  -- deterministic, and therefore able to be evidence

Giving the gate a face would undo the whole point: a non-deterministic judge cannot
produce an audit record. Things that think get faces; things that decide get stamps.
"""
from __future__ import annotations

INK = "#191919"

# ── the roster, from the deck ────────────────────────────────────────────────
STATIONS = [
    {"id": "ST-01", "name": "Understand", "role": "read the graph",
     "kind": "agent", "model": "haiku / low", "colour": "#4a90e2",
     "blurb": "Loads the intent graph — terms, constraints, rules in scope — before a line is written."},
    {"id": "ST-02", "name": "Disambiguate", "role": "human gate",
     "kind": "human", "model": "a person", "colour": "#e5e5e5",
     "blurb": "Underspecified dimensions come back as pending questions. Nothing proceeds on a guess."},
    {"id": "ST-03", "name": "Design", "role": "the Architect",
     "kind": "agent", "model": "opus / high", "colour": "#b47cff",
     "blurb": "Turns intent into an approach, against the rubric rather than against taste."},
    {"id": "ST-04", "name": "Develop", "role": "writes code",
     "kind": "agent", "model": "opus / high", "colour": "#ff6b4a",
     "blurb": "Builds the change. One column of the traceability schema, not the whole solution."},
    {"id": "ST-04b", "name": "Clean", "role": "simplify, not change",
     "kind": "agent", "model": "opus / high", "colour": "#ff8fd0",
     "blurb": "Goes back over the change and simplifies it. Behaviour must not move."},
    {"id": "ST-05", "name": "Test", "role": "adversarial coverage",
     "kind": "agent", "model": "opus / high", "colour": "#00b67a",
     "blurb": "A separate agent, so the author is never grading its own coverage."},
    {"id": "ST-06", "name": "Verify", "role": "4 refuting lenses",
     "kind": "agent", "model": "opus / high", "colour": "#8b1538",
     "blurb": "Four critics try to refute the work — correctness, coverage, security, reproduce."},
    {"id": "ST-07", "name": "Assemble", "role": "one gated PR",
     "kind": "machine", "model": "script", "colour": "#fff",
     "blurb": "Collects the team's output into a single pull request. No judgement, no model."},
    {"id": "ST-08", "name": "CI gates", "role": "the judge",
     "kind": "machine", "model": "keelspec", "colour": "#fbcc00",
     "blurb": "The PAC-NNN rubric runs on every PR — including an agent's own build PR."},
    {"id": "ST-09", "name": "Human merge", "role": "a person decides",
     "kind": "human", "model": "a person", "colour": "#e5e5e5",
     "blurb": "Agents never auto-merge. Autonomy stops exactly where the stakes rise."},
    {"id": "ST-10", "name": "Production", "role": "the oracle",
     "kind": "machine", "model": "reality", "colour": "#fff",
     "blurb": "The only judge that cannot be argued with. Findings feed back into intent."},
]

# ST-06's four refuting lenses, wording from the deck.
LENSES = [
    ("correctness", "#ff6b4a",
     "Find an input where it does the WRONG thing — and do the tests pass vacuously?"),
    ("coverage", "#00b67a",
     "Does every acceptance criterion map to a test that would catch its regression?"),
    ("security", "#4a90e2",
     "Payments lens: authz, trust boundaries, injection, PII, secrets, spend / consent."),
    ("reproduce", "#b47cff",
     "Ignore the happy path: concurrency, partial failure, retries / idempotency, rollback."),
]

FANOUT = [
    ("Document", "#4a90e2", "the spec, the glossary, the decision record"),
    ("Roadmap", "#b47cff", "what is planned, and what it depends on"),
    ("Operations", "#00b67a", "runbooks, monitors, the things on call needs"),
]


# ── avatars ──────────────────────────────────────────────────────────────────
def _face(colour: str, seed: int) -> str:
    """A geometric portrait. Varied by seed so the roster does not look cloned."""
    brow = ["M13 17 L23 15", "M13 15 L23 17", "M13 16 L23 16"][seed % 3]
    mouth = ["M15 30 Q24 35 33 30", "M15 32 L33 32", "M15 33 Q24 28 33 33"][seed % 3]
    visor = seed % 2 == 0
    eyes = (f'<rect x="11" y="19" width="26" height="9" rx="4.5" fill="{INK}"/>'
            f'<circle cx="17" cy="23.5" r="2" fill="#fff"/>'
            f'<circle cx="31" cy="23.5" r="2" fill="#fff"/>') if visor else (
            f'<circle cx="17" cy="23" r="3.6" fill="{INK}"/>'
            f'<circle cx="31" cy="23" r="3.6" fill="{INK}"/>')
    return (
        f'<svg viewBox="0 0 48 48" class="st-avatar" aria-hidden="true">'
        f'<rect x="2" y="2" width="44" height="44" rx="12" fill="{colour}" stroke="{INK}" stroke-width="3"/>'
        f'<path d="M8 44 Q24 30 40 44" fill="{INK}" opacity="0.18"/>'
        f'<circle cx="24" cy="22" r="15" fill="#fff" stroke="{INK}" stroke-width="3"/>'
        f'<path d="{brow}" stroke="{INK}" stroke-width="2.4" fill="none" stroke-linecap="round"/>'
        f'<path d="{brow.replace("13", "25").replace("23", "35")}" stroke="{INK}" stroke-width="2.4" '
        f'fill="none" stroke-linecap="round" opacity="0"/>'
        f'{eyes}'
        f'<path d="{mouth}" stroke="{INK}" stroke-width="2.6" fill="none" stroke-linecap="round"/>'
        f'</svg>')


def _person() -> str:
    """A human station. A figure, not a face -- this is a role, not a personality."""
    return (
        f'<svg viewBox="0 0 48 48" class="st-avatar" aria-hidden="true">'
        f'<rect x="2" y="2" width="44" height="44" rx="12" fill="#fff" stroke="{INK}" stroke-width="3"/>'
        f'<circle cx="24" cy="18" r="7.5" fill="{INK}"/>'
        f'<path d="M10 42 Q24 25 38 42 Z" fill="{INK}"/>'
        f'</svg>')


def _plate(colour: str) -> str:
    """A deterministic station. A stamp: no eyes, nothing to persuade."""
    return (
        f'<svg viewBox="0 0 48 48" class="st-avatar" aria-hidden="true">'
        f'<rect x="2" y="2" width="44" height="44" rx="12" fill="{colour}" stroke="{INK}" stroke-width="3"/>'
        f'<rect x="11" y="13" width="26" height="5" rx="2.5" fill="{INK}"/>'
        f'<rect x="11" y="22" width="26" height="5" rx="2.5" fill="{INK}"/>'
        f'<rect x="11" y="31" width="16" height="5" rx="2.5" fill="{INK}"/>'
        f'</svg>')


def avatar(station: dict, index: int) -> str:
    if station["kind"] == "agent":
        return _face(station["colour"], index)
    if station["kind"] == "human":
        return _person()
    return _plate(station["colour"])


KIND_LABEL = {"agent": "agent", "human": "human", "machine": "deterministic"}


def rail_cards() -> str:
    """The scrolling hero rail."""
    out = []
    for i, s in enumerate(STATIONS):
        badge_style = ("background:#191919;color:#fbcc00"
                       if s["id"] == "ST-08" else "")
        out.append(f"""<article class="station" data-kind="{s['kind']}">
  <div class="st-head">
    {avatar(s, i)}
    <div>
      <span class="st-id">{s['id']}</span>
      <h3 class="st-name">{s['name']}</h3>
    </div>
  </div>
  <p class="st-role">{s['role']}</p>
  <code class="st-model">{s['model']}</code>
  <span class="badge st-kind" style="{badge_style}">{KIND_LABEL[s['kind']]}</span>
</article>""")
    return "".join(out)
