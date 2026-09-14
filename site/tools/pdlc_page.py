"""The /lifecycle page: one lifecycle, automated gates, a provable audit trail.

This is the positioning page. The diagram is the argument: product intent and code
live in one repository, pass through one gate, and fan out to every surface -- with
a check on each edge and an audit record of every run.
"""
from __future__ import annotations

INK = "#191919"
YEL = "#fbcc00"
GRN = "#00b67a"
BLU = "#4a90e2"
ORA = "#ff6b4a"
PUR = "#b47cff"
CRM = "#fff9e6"


def _chip(x, y, w, label, fill="#fff", size=13):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="30" rx="7" fill="{fill}" '
            f'stroke="{INK}" stroke-width="2.5"/>'
            f'<text x="{x + w / 2}" y="{y + 20}" text-anchor="middle" '
            f'font-family="IBM Plex Mono, monospace" font-size="{size}" fill="{INK}">{label}</text>')


def _box(x, y, w, h, title, fill="#fff"):
    return (f'<rect x="{x + 5}" y="{y + 5}" width="{w}" height="{h}" rx="14" fill="{INK}"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" '
            f'stroke="{INK}" stroke-width="3.5"/>'
            f'<text x="{x + 18}" y="{y + 30}" font-family="Anton, Impact, sans-serif" '
            f'font-size="19" letter-spacing="0.4" fill="{INK}">{title}</text>')


def _arrow(x1, y1, x2, y2, colour=INK):
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{colour}" '
            f'stroke-width="3.5" marker-end="url(#head)"/>')


def diagram() -> str:
    p = ['<svg viewBox="0 0 1160 600" role="img" '
         'aria-label="Product intent and code share one repository, one gate, and fan out '
         'to every surface, with a check on each edge and an audit record of every run." '
         'style="width:100%;height:auto">']
    p.append(f'<defs><marker id="head" markerWidth="9" markerHeight="9" refX="7" refY="4.5" '
             f'orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="{INK}"/></marker></defs>')

    # ── stage 1: intent ─────────────────────────────────────────────────────
    p.append(_box(20, 60, 250, 250, "PRODUCT INTENT", CRM))
    for i, (label, colour) in enumerate([("terms", "#fff"), ("rules", "#fff"),
                                         ("features", "#fff"), ("decisions", "#fff")]):
        p.append(_chip(42, 92 + i * 44, 206, label, colour))
    p.append(f'<text x="145" y="330" text-anchor="middle" font-family="IBM Plex Sans, sans-serif" '
             f'font-size="13" fill="#6b6b6b">markdown + frontmatter, in your repo</text>')

    # ── gate 1 ──────────────────────────────────────────────────────────────
    p.append(_arrow(275, 185, 340, 185))
    p.append(_box(345, 105, 190, 160, "THE GATE", YEL))
    p.append(f'<text x="363" y="152" font-family="IBM Plex Mono, monospace" font-size="13" '
             f'fill="{INK}">keelspec validate</text>')
    for i, code in enumerate(["PAC-001  schema", "PAC-020  graph", "PAC-060  staleness"]):
        p.append(f'<text x="363" y="{178 + i * 22}" font-family="IBM Plex Mono, monospace" '
                 f'font-size="11.5" fill="{INK}">{code}</text>')
    p.append(f'<text x="440" y="288" text-anchor="middle" font-family="IBM Plex Sans, sans-serif" '
             f'font-size="13" fill="#6b6b6b">non-zero exit blocks the merge</text>')

    # ── stage 2: bundle ─────────────────────────────────────────────────────
    p.append(_arrow(540, 185, 605, 185))
    p.append(_box(610, 125, 200, 120, "ONE BUNDLE", "#fff"))
    p.append(f'<text x="628" y="168" font-family="IBM Plex Mono, monospace" font-size="12" '
             f'fill="{INK}">product.generated</text>')
    p.append(f'<text x="628" y="186" font-family="IBM Plex Mono, monospace" font-size="12" '
             f'fill="{INK}">.json</text>')
    p.append(f'<text x="628" y="215" font-family="IBM Plex Sans, sans-serif" font-size="12" '
             f'fill="#6b6b6b">committed, byte-stable</text>')

    # ── fan-out ─────────────────────────────────────────────────────────────
    # The fan-out from pharthing's roster -- Document, Roadmap, Operations. An
    # earlier version of this diagram invented Code/Tests/In-app/LLM-context, which
    # described a pattern rather than the model this product actually implements.
    targets = [("Document", 70, BLU), ("Roadmap", 178, PUR), ("Operations", 286, GRN)]
    for label, y, colour in targets:
        p.append(_arrow(815, 185, 930, y + 20))
        p.append(f'<rect x="940" y="{y + 4}" width="200" height="38" rx="9" fill="{colour}" '
                 f'stroke="{INK}" stroke-width="3"/>')
        p.append(f'<text x="1040" y="{y + 29}" text-anchor="middle" '
                 f'font-family="Anton, Impact, sans-serif" font-size="16" fill="{INK}">{label}</text>')

    # The fan-out legend sits under the bundle, clear of the arrows -- placing it
    # inside the fan made it collide with five diagonals and become unreadable.
    p.append(f'<rect x="610" y="268" width="200" height="32" rx="8" fill="#fff" '
             f'stroke="{INK}" stroke-width="2.5" stroke-dasharray="6 4"/>')
    p.append(f'<text x="710" y="289" text-anchor="middle" font-family="IBM Plex Mono, monospace" '
             f'font-size="12.5" fill="{INK}">PAC-9xx on each edge</text>')
    p.append(f'<text x="710" y="320" text-anchor="middle" font-family="IBM Plex Sans, sans-serif" '
             f'font-size="12.5" fill="#6b6b6b">your plugin checks</text>')

    # ── audit rail ──────────────────────────────────────────────────────────
    p.append(f'<rect x="25" y="400" width="1105" height="150" rx="16" fill="{INK}"/>')
    p.append(f'<text x="55" y="440" font-family="Anton, Impact, sans-serif" font-size="21" '
             f'fill="{YEL}" letter-spacing="0.5">THE AUDIT TRAIL</text>')
    p.append(f'<text x="55" y="466" font-family="IBM Plex Sans, sans-serif" font-size="14" '
             f'fill="#c9c9c9">Every box above is a file in git. Every arrow is a check that ran in CI.</text>')

    facts = [
        ("Every change", "is a reviewed commit"),
        ("Every gate run", "is a CI record"),
        ("Every finding", "has a stable code"),
        ("Every bundle", "is byte-reproducible"),
    ]
    for i, (a, b) in enumerate(facts):
        x = 55 + i * 272
        p.append(f'<rect x="{x}" y="486" width="250" height="46" rx="9" fill="#232323" '
                 f'stroke="#3a3a3a" stroke-width="2"/>')
        p.append(f'<text x="{x + 16}" y="506" font-family="IBM Plex Sans, sans-serif" '
                 f'font-size="13" font-weight="700" fill="{GRN}">{a}</text>')
        p.append(f'<text x="{x + 16}" y="523" font-family="IBM Plex Sans, sans-serif" '
                 f'font-size="12.5" fill="#b8b8b8">{b}</text>')

    p.append("</svg>")
    return "".join(p)


BODY = f"""<main>
<section class="section">
  <div class="wrap">
    <div class="section-head" style="max-width:52rem">
      <span class="eyebrow">Lifecycle</span>
      <h1 style="font-size:clamp(2.5rem,6vw,4rem);margin-top:0.7rem">One lifecycle, not two.</h1>
      <p class="lede">Most organisations run a <strong>product development lifecycle (PDLC)</strong>
        and a <strong>software development lifecycle (SDLC)</strong> side by side, connected by
        meetings. The SDLC has been mechanised for thirty years &mdash; compilers, type checkers,
        tests, continuous integration (CI). The PDLC has almost none of it. KeelSpec puts both in
        the same repository, behind the same gate, with the same evidence trail.</p>
    </div>

    <div class="card" style="padding:1.6rem 1.4rem;overflow-x:auto">
      {diagram()}
    </div>

    <p class="muted" style="margin-top:1rem;font-size:0.92rem;max-width:52rem">
      <strong>What ships today:</strong> <code style="font-family:var(--mono)">keelspec
      orchestrate</code> runs ST-01 to ST-06, and <code style="font-family:var(--mono)">keelspec
      validate</code> is ST-08. Assembling a pull request (ST-07) and reading production
      back into intent (ST-10) are your pipeline's job &mdash; the library has no git,
      no network and no way to merge, by design.
    </p>
  </div>
</section>

<hr class="rule">

<section class="section">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">The asymmetry</span>
      <h2>Your code has a compiler. Your product model has hope.</h2>
    </div>
    <div class="steps">
      <article class="card step">
        <div class="step-n">SDLC</div>
        <h3>Mechanised</h3>
        <p>A rename breaks every caller, loudly, in seconds. Types are checked, tests run on
          every push, and nothing merges red. Nobody argues about whether this is worth it.</p>
      </article>
      <article class="card step">
        <div class="step-n">PDLC</div>
        <h3>Unmechanised</h3>
        <p>A concept changes meaning and every document that assumed the old one stays
          syntactically perfect and semantically wrong. No tool can see the dependency, because
          it was written in English.</p>
      </article>
      <article class="card step">
        <div class="step-n">→</div>
        <h3>The fix is not discipline</h3>
        <p>It is the same fix the SDLC already made: declare the structure, check it on every
          change, and fail the build when it stops being true.</p>
      </article>
    </div>
  </div>
</section>

<section class="section band-cream">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Automation</span>
      <h2>Checks live on the edges.</h2>
      <p class="lede">Intent fans out. A rule becomes a feature, a ticket, an implementation, a
        test, a doc page, a support macro. Every one of those edges is where drift enters, and
        every one of them can carry a check.</p>
    </div>

    <div class="diags">
      <article class="diag" style="--c:#4a90e2; --c2:#fbcc00">
        <div class="diag-code">INSIDE</div>
        <h3>The intent graph</h3>
        <p>Required fields, id integrity, allowed values, and every reference resolving.
          Shipped in the core, running today.</p>
        <code class="sample">PAC-001 &middot; PAC-010 &middot; PAC-020 &middot; PAC-030</code>
        <span class="badge">Core</span>
      </article>

      <article class="diag" style="--c:#fbcc00; --c2:#191919">
        <div class="diag-code">ACROSS</div>
        <h3>Intent to build</h3>
        <p>The committed bundle still matches the sources that produced it &mdash; so what you
          ship and what you wrote cannot silently part company.</p>
        <code class="sample">PAC-060 &middot; staleness</code>
        <span class="badge" style="background:#191919;color:#fbcc00">Core</span>
      </article>

      <article class="diag" style="--c:#00b67a; --c2:#fff">
        <div class="diag-code">OUTWARD</div>
        <h3>Product to code</h3>
        <p>The boundary nothing else checks. Does this feature's claimed source path still
          exist? Does every business rule have a test that names its id? Written as plugin
          validators in your own code range.</p>
        <code class="sample">PAC-9xx &middot; your checks</code>
        <span class="badge">Plugin</span>
      </article>
    </div>

    <div class="card" style="margin-top:1.6rem;padding:1.5rem">
      <h3 style="margin-bottom:0.8rem">The boundary check, in eight lines</h3>
<pre><code><span class="y">@reg.validator</span>
<span class="o">def</span> <span class="p">code_paths_exist</span>(bundle, config, root, report):
    <span class="o">for</span> f <span class="o">in</span> bundle[<span class="s">"features"</span>]:
        <span class="o">for</span> path <span class="o">in</span> f.get(<span class="s">"code"</span>) <span class="o">or</span> []:
            <span class="o">if not</span> (root / path).exists():
                report.add(<span class="s">"PAC-900"</span>,
                           <span class="s">f"missing {{path}}"</span>,
                           f[<span class="s">"_file"</span>])</code></pre>
      <p style="margin-top:1rem;font-size:0.95rem;color:#444">A feature that claims code which
        no longer exists is a documented product that is not the shipped product. That is one
        validator, and it is the whole category in miniature.</p>
    </div>
  </div>
</section>

<section class="section band-ink">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow" style="color:var(--yellow)">Audit</span>
      <h2>Evidence, not screenshots.</h2>
      <p class="lede" style="color:#b8b8b8">The question an auditor actually asks is: how do you
        know your documented rules match your implementation, and can you prove it for any date?
        Most organisations answer with a screenshot of a wiki page.</p>
    </div>

    <div class="timeline">
      <article class="tl">
        <div class="tl-time">01</div>
        <div>
          <h3>The record is the repository</h3>
          <p>Every artifact is a file, every change is a reviewed commit with an author and a
            timestamp, and every state is recoverable by checking out a SHA. There is no separate
            system of record to reconcile, because the record is the thing itself.</p>
        </div>
      </article>
      <article class="tl">
        <div class="tl-time">02</div>
        <div>
          <h3>The control is the gate</h3>
          <p><code>keelspec validate</code> runs on every pull request (PR) and its exit code decides
            whether the change merges. That is a control with an enforcement mechanism, not a
            policy document asking people to be careful.</p>
        </div>
      </article>
      <article class="tl pass">
        <div class="tl-time">03</div>
        <div>
          <h3>The evidence is reproducible</h3>
          <p>Bundles are byte-stable: sorted keys, fixed formatting, no timestamps. Check out any
            commit, rebuild, and get identical bytes. An assertion about what the product model
            was on a given date is verifiable rather than asserted.</p>
          <span class="tag ok">deterministic</span>
        </div>
      </article>
      <article class="tl">
        <div class="tl-time">04</div>
        <div>
          <h3>The record is exportable</h3>
          <p><code>keelspec evidence -o build/evidence.json</code> emits what was checked, when,
            on which commit, and with what result &mdash; every artifact, the config and the
            bundle carrying a SHA-256. An auditor verifies it by recomputing digests, not by
            trusting the issuer. For a date in the past, check out that commit and run it again.</p>
          <span class="tag ok">content-addressed</span>
        </div>
      </article>
      <article class="tl">
        <div class="tl-time">05</div>
        <div>
          <h3>The findings are stable</h3>
          <p>Diagnostics carry codes that are never renumbered, so a control can be described
            once and matched on forever &mdash; by CI, by a dashboard, or by whoever is asking.</p>
        </div>
      </article>
    </div>

    <p class="lede" style="color:#b8b8b8;margin-top:2rem;max-width:46rem">This is why the engine
      was built inside a payments platform first. In a regulated domain the distance between
      "what we documented" and "what we shipped" is not an inconvenience &mdash; it is the finding.</p>
  </div>
</section>

<section class="section cta">
  <div class="wrap">
    <h2>Put both lifecycles behind one gate.</h2>
    <p class="lede">Start with a glossary and one CI step. Add boundary checks when the graph is
      big enough to need them.</p>
    <div class="cta-actions">
      <a class="btn btn-primary btn-lg" href="/#start">Get started</a>
      <a class="btn btn-lg" href="/blog/">Read the blog</a>
    </div>
  </div>
</section>
</main>"""
