"""Rebuild the generated regions of the homepage.

`public/index.html` is hand-authored source -- the head, nav, hero copy, the
product-as-code sections, FAQ and footer are edited there directly. This script owns
the regions that are *derived* from data, so they cannot drift from it:

1. The hero rail and its label, from the ST-01..ST-10 roster in `stations.py`.
2. The positioning sections, in this order, right after the hero:
     story     spec -> any agent -> gate
     fastpdlc  the ten-station method, automated line vs hand-off points
     lenses    ST-06's refuting critics
     evidence  `keelspec evidence` and `--verify` as the audit trail
     compare   where KeelSpec sits relative to agent platforms
     proof     the payments platform, linking the case study

Every claim in these sections is checked against the README, AI-GOVERNANCE.md or
the code. When the product changes, change the claim here and re-run.

Each section is found by its `<!-- ══ name` marker and replaced whole, then placed
before the "how it works" section. Running the script twice gives the same file.

Run from site/:  python tools/rebuild_home.py
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from stations import (LENSES, STATIONS, _face, fastpdlc_diagram,  # noqa: E402
                      rail_cards, roster_counts)

HOME = pathlib.Path(__file__).resolve().parent.parent / "public" / "index.html"
MARK = "<!-- ══ "
ANCHOR = "<!-- ══ how it works"
CASE_STUDY = "/blog/payments-case-study.html"
REPO = "https://github.com/Tech-Res-Group/keelspec"

NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
                7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def marker(name: str) -> str:
    return f"{MARK}{name} " + "═" * max(4, 66 - len(name)) + " -->"


# ── sections ─────────────────────────────────────────────────────────────────
STORY = """
<section class="section" id="story">
  <div class="wrap">
    <div class="section-head reveal">
      <span class="eyebrow">How it works</span>
      <h2>Spec. Any agent. Gate.</h2>
      <p class="lede">KeelSpec owns the three things a builder should not own about its own
        work: the intent it is judged against, the check that judges it, and the record of
        what passed.</p>
    </div>

    <ol class="story">
      <li class="card story-step reveal">
        <div class="step-n">01</div>
        <span class="eyebrow">The spec</span>
        <h3>Typed product intent, in your repo.</h3>
        <p>Features, rules, decisions, whatever types you declare: markdown with typed frontmatter,
          validated as a graph and compiled into a committed bundle. Open questions stop the
          line before design, and named roles accept the spec.</p>
        <p class="story-key"><code>PAC-060</code> fails the build when the committed bundle
          drifts from its sources.</p>
      </li>

      <li class="card story-step reveal">
        <div class="step-n">02</div>
        <span class="eyebrow">Any agent</span>
        <h3>The builder is swappable.</h3>
        <p>Every station runs through one <code>Runner</code> seam. The library ships runners
          for the Anthropic API and for any OpenAI-compatible endpoint, such as your own model
          gateway, and you can supply your own. A pull request from any agent, or any
          person, meets the same gate.</p>
        <p class="story-key"><span class="badge badge-road">Roadmap</span> Ready-made
          adapters for Claude Code, Codex, Devin and Copilot's coding agent.</p>
      </li>

      <li class="card story-step reveal">
        <div class="step-n">03</div>
        <span class="eyebrow">The gate</span>
        <h3>Deterministic first, then a person.</h3>
        <p><code>keelspec validate</code> calls no model. The same tree gets the same
          <code>PAC-NNN</code> verdict on every pull request, and the exit code is the
          contract. Inside the line, five critics try to refute each change, with an optional
          sixth on a different model provider.</p>
        <p class="story-key">Nothing auto-merges. A human does.</p>
      </li>
    </ol>
  </div>
</section>
"""

FASTPDLC = """
<section class="section band-cream" id="fastpdlc">
  <div class="wrap">
    <div class="section-head reveal">
      <span class="eyebrow">The method</span>
      <h2>KeelSpec runs the FastPDLC lifecycle.</h2>
      <p class="lede">Ten stations from a written-down story to production. KeelSpec automates
        the engineering segment, from understanding the spec to a change that has been built,
        tested and attacked. Everything after the pull request is a hand-off to the process
        you already run.</p>
    </div>

    %s

    <p class="pdlc-more reveal">The scope is deliberate. See
      <a href="/lifecycle.html">the lifecycle page</a> and
      <a href="%s/blob/main/AI-GOVERNANCE.md">AI-GOVERNANCE.md</a> for what the line does
      with models and data.</p>
  </div>
</section>
"""

LENSES_SECTION = """
<section class="section" id="lenses">
  <div class="wrap">
    <div class="section-head reveal">
      <span class="eyebrow">ST-06 &middot; Verify</span>
      <h2>Five agent critics, each trying to refute the work.</h2>
      <p class="lede">The agent that builds a change does not get to grade it. A separate
        station attacks the result through five independent lenses, each defaulting to
        <em>refuted</em> unless convinced. Four ask whether the change meets its specification;
        the fifth asks whether the business process around it survives.</p>
    </div>

    <div class="lenses">
      %s
    </div>

    <div class="proof-note reveal" style="margin-top:2rem">
      <span class="badge">Optional sixth</span>
      <p><code>--cross-provider</code> adds a verdict from a model outside the builder's family,
        so it cannot share the builder's blind spots. It sees a diff summary and test notes,
        <strong>without</strong> product context. If the call fails, it abstains rather than
        blocking.</p>
    </div>
  </div>
</section>
"""

EVIDENCE = """
<section class="section band-ink" id="evidence">
  <div class="wrap split">
    <div class="reveal">
      <span class="eyebrow" style="color:var(--yellow)">Evidence</span>
      <h2 style="margin-top:0.9rem">The audit trail an SDLC or model-risk review asks for.</h2>
      <p class="lede" style="margin-top:1.1rem;color:#c9c9c9">The review starts with
        <em>&ldquo;prove your documented rules matched what you shipped.&rdquo;</em> KeelSpec
        answers with files in your repository, checked by recomputing digests rather than by
        trusting whoever produced them.</p>
      <ul class="feature-list ev-list">
        <li>
          <span class="n">#</span>
          <span><b><code>keelspec evidence</code></b><span>A content-addressed record: the commit,
            whether the tree was clean, the tool version, the config, a SHA-256 for every
            artifact and the bundle, every finding, and the result. Its exit code follows
            <code>validate</code>, so CI gates and records in one step.</span></span>
        </li>
        <li>
          <span class="n">&#10003;</span>
          <span><b><code>--verify</code></b><span>Recomputes every digest against the tree. For an
            old record, check out its commit and run it again: bundles are byte-stable.</span></span>
        </li>
        <li>
          <span class="n">&#9998;</span>
          <span><b>Run records and named approvals</b><span>Every orchestrated run keeps each
            station's output, every verdict, the triage cause and the risk tier. Required
            approvers sign the spec by role, and the commit that fills in the name is the
            signature.</span></span>
        </li>
      </ul>
      <p class="ev-scope">KeelSpec produces evidence. It does not make you compliant and holds no
        certification. What the evidence must show is your organisation's policy.</p>
    </div>

    <div class="term reveal">
      <div class="term-bar">
        <span class="term-dot" style="background:#ff6b4a"></span>
        <span class="term-dot" style="background:#fbcc00"></span>
        <span class="term-dot" style="background:#00b67a"></span>
        <span class="term-name">ci / evidence</span>
      </div>
      <div class="term-body">
        <span class="l t-cmd">keelspec evidence -o build/evidence.json</span>
        <span class="l t-dim">wrote build/evidence.json</span>
        <span class="l">&nbsp;</span>
        <span class="l t-cmd">keelspec evidence --verify build/evidence.json</span>
        <span class="l t-ok">evidence verified: every digest still matches</span>
        <span class="l t-ok">(recorded 2026-11-16T21:07:01Z)</span>
        <span class="l">&nbsp;</span>
        <span class="l t-dim"># build/evidence.json, excerpt</span>
        <span class="l">&quot;schema&quot;: &quot;keelspec-evidence/1&quot;,</span>
        <span class="l">&quot;result&quot;: <span class="t-ok">&quot;pass&quot;</span>,</span>
        <span class="l">&quot;repository&quot;: { &quot;commit&quot;: &quot;b69d32c&hellip;&quot;, &quot;clean&quot;: true },</span>
        <span class="l">&quot;bundle&quot;: { &quot;matches_sources&quot;: true,</span>
        <span class="l">            &quot;sha256&quot;: &quot;9f50b849&hellip;&quot; },</span>
        <span class="l">&quot;checks&quot;: { &quot;errors&quot;: 0, &quot;warnings&quot;: 0 }</span>
      </div>
    </div>
  </div>
</section>
"""

COMPARE = """
<section class="section" id="compare">
  <div class="wrap">
    <div class="section-head reveal">
      <span class="eyebrow">Where it fits</span>
      <h2>On top of your agents, not instead of them.</h2>
      <p class="lede">Devin, Factory.ai, Claude Code, Codex and Copilot's coding agent build
        software. KeelSpec does not compete with them on building. It is the part a builder
        cannot credibly supply for itself: a check it does not control.</p>
    </div>

    <div class="fit reveal">
      <div class="fit-col">
        <h3>Your agent fleet brings</h3>
        <ul>
          <li>The builder, and whatever runs it: sandboxes, parallel runs, IDE and chat
            integrations, ticket intake.</li>
          <li>Its own review and testing, if you use them.</li>
          <li>Its own pricing, hosting and enterprise terms.</li>
        </ul>
      </div>
      <div class="fit-col fit-keel">
        <h3>KeelSpec adds</h3>
        <ul>
          <li>Typed, versioned intent the change is judged against, with <code>PAC-060</code>
            on drift.</li>
          <li>A gate that calls no model and belongs to no agent vendor or model provider.</li>
          <li>Five refuting critics, an optional sixth on a different model provider, and
            triage before repair.</li>
          <li>Evidence records that are verified by recomputation.</li>
          <li>All of it in your repo and your CI: <code>pip install keelspec</code>, a GitHub
            Action, Apache-2.0.</li>
        </ul>
      </div>
      <div class="fit-col fit-not">
        <h3>KeelSpec does not</h3>
        <ul>
          <li>Run agents in managed sandboxes or in the cloud.</li>
          <li>Replace your CI, CD or change management. ST-07 to ST-10 are hand-offs.</li>
          <li>Provide SSO, or hold SOC 2 or any other certification.</li>
          <li>Merge anything.</li>
        </ul>
      </div>
    </div>

    <div class="proof-note reveal" style="margin-top:2rem">
      <span class="badge badge-road">Roadmap</span>
      <p>Not built yet: ready-made builder adapters for Claude Code, Codex, Devin and Copilot's
        coding agent, and intake that turns GitHub Issues, Linear or Jira tickets into feature
        files with acceptance criteria. Today, <code>keelspec runs</code> already reports
        first-pass rate and refutations by lens.</p>
    </div>
  </div>
</section>
"""

PROOF = """
<section class="section band-cream" id="proof">
  <div class="wrap">
    <div class="section-head reveal">
      <span class="eyebrow">Used in production</span>
      <h2>The only product gate at a payments platform.</h2>
      <p class="lede">KeelSpec is the product-as-code engine of the
        <strong>pharthing / KibiPay</strong> payments platform. It was extracted from a working
        system so other teams could use it.</p>
    </div>

    <div class="proof-note reveal">
      <span class="badge">Parity test</span>
      <p>pharthing's CI runs <strong>keelspec validate</strong> as its sole product gate, through
        a plugin that adds its domain checks. A <strong>byte-identical parity test</strong> proves
        the extracted engine produces exactly the bundle the in-house one did.</p>
    </div>

    <p class="reveal" style="margin-top:1.6rem">
      <a class="btn btn-primary" href="%s">Read the case study</a>
    </p>
  </div>
</section>
"""


def lens_cards() -> str:
    """Each critic gets a face, seeded differently so five agents do not read as one
    agent copied five times. These are ST-06 agents, so the face is accurate here."""
    out = []
    for i, (name, colour, question) in enumerate(LENSES):
        out.append(f"""<article class="lens reveal" style="--c:{colour}">
        <div class="lens-head">{_face(colour, i + 2)}<h3>{name}</h3></div>
        <p>{question}</p>
        <span class="badge">agent critic</span>
      </article>""")
    return "\n      ".join(out)


def sections() -> list[tuple[str, str]]:
    return [
        ("story", STORY),
        ("fastpdlc", FASTPDLC % (fastpdlc_diagram(), REPO)),
        ("the refuting lenses", LENSES_SECTION % lens_cards()),
        ("evidence", EVIDENCE),
        ("where it fits", COMPARE),
        ("proof", PROOF % CASE_STUDY),
    ]


# ── editing helpers ──────────────────────────────────────────────────────────
def remove_section(html: str, name: str) -> str:
    """Drop the region from `<!-- ══ name` up to the next section marker."""
    start = html.find(f"{MARK}{name} ")
    if start < 0:
        return html
    end = html.find(MARK, start + len(MARK))
    return html[:start] + html[end:]


def rail_label() -> str:
    c = roster_counts()
    return (f'<p class="rail-label">The line &mdash; {NUMBER_WORDS[c["agent"]]} agent stations, '
            f'{NUMBER_WORDS[c["human"]]} human gates, '
            f'{NUMBER_WORDS[c["machine"]]} deterministic</p>')


def main() -> int:
    html = HOME.read_text(encoding="utf-8")

    # ── 1. hero rail and its label ──────────────────────────────────────────
    # Anchor on the next landmark, never on a closing-tag pattern: the cards end
    # the same way the rail does, so slicing on `</div>` cuts in the wrong place on
    # a second run.
    start = html.index('<div class="rail" aria-hidden="true">')
    end = html.index('<div class="wrap hero-grid">')
    html = html[:start] + (
        '<div class="rail" aria-hidden="true">\n    '
        '<div class="rail-track" id="railTrack">\n      '
        + rail_cards()
        + "\n    </div>\n  </div>\n\n  ") + html[end:]
    html = re.sub(r'<p class="rail-label">.*?</p>', rail_label(), html, count=1)

    # ── 2. positioning sections: remove wherever they are, re-insert in order ─
    built = sections()
    for name, _ in built:
        html = remove_section(html, name)
    block = "".join(f"{marker(name)}{body}\n" for name, body in built)
    html = html.replace(ANCHOR, block + ANCHOR, 1)

    HOME.write_text(html, encoding="utf-8", newline="\n")
    print(f"rebuilt {HOME.name}")
    print(f"  rail       : {len(STATIONS)} stations")
    print(f"  lenses     : {len(LENSES)}")
    print(f"  sections   : {', '.join(name for name, _ in built)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
