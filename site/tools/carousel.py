"""A LinkedIn carousel, as a print-ready page.

LinkedIn document posts are PDFs. Rather than reach for a design tool, the slides
are HTML in the site's own system and the PDF comes from the browser's print
dialogue — so the carousel cannot drift from the brand, and editing a line is
editing a string.

The station faces are imported from `stations.py`, not redrawn, so the carousel and
the homepage rail can never disagree about what an agent looks like.

Slides are 1080x1350 (4:5), which is what LinkedIn crops to on mobile. `@page`
matches exactly and every slide is its own page, so "Save as PDF" with margins off
and background graphics on gives one slide per page with no bleed.

    python tools/carousel.py    ->  public/carousel.html
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from stations import STATIONS, avatar  # noqa: E402  (one source for the faces)

OUT = pathlib.Path(__file__).resolve().parent.parent / "public" / "carousel.html"

# the site's palette, verbatim
INK, PAPER, YEL = "#191919", "#ffffff", "#fbcc00"
GRN, ORA, BLU, PUR, PNK, RED, CRM = (
    "#00b67a", "#ff6b4a", "#4a90e2", "#b47cff", "#ff8fd0", "#8b1538", "#fff9e6")

LOGO = (
    '<svg viewBox="0 0 40 40" class="mark" aria-hidden="true">'
    '<rect x="1.6" y="1.6" width="36.8" height="36.8" rx="9" fill="#191919"/>'
    '<path d="M10.5 21.5 L17 28 L29.5 12.5" fill="none" stroke="#fbcc00" '
    'stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round"/>'
    '<circle cx="10.5" cy="21.5" r="3.6" fill="#fff"/>'
    '<circle cx="29.5" cy="12.5" r="3.6" fill="#00b67a"/></svg>')


def slide(n: int, body: str, *, bg: str = PAPER, dark: bool = False,
          footer: bool = True) -> str:
    cls = "slide" + (" dark" if dark else "")
    foot = (f'<div class="foot"><span class="fmark">{LOGO}<b>KeelSpec</b></span>'
            f'<span class="num">{n:02d}</span></div>') if footer else ""
    return f'<section class="{cls}" style="--bg:{bg}">{body}{foot}</section>'


def station_card(index: int) -> str:
    s = STATIONS[index]
    kind = {"agent": "agent", "human": "human", "machine": "deterministic"}[s["kind"]]
    return f"""<div class="stn" data-kind="{s['kind']}">
      {avatar(s, index)}
      <div class="stn-t"><b>{s['id']}</b>{s['name']}</div>
      <span class="chip">{kind}</span>
    </div>"""


SLIDES: list[str] = []

# ── 1 · the hook ─────────────────────────────────────────────────────────────
SLIDES.append(slide(1, f"""
  <div class="pad">
    <span class="eyebrow">Product-as-code</span>
    <h1 class="mega">Someone<br>renames<br>one <span class="hl">term.</span></h1>
    <div class="card mono shadow-xl" style="margin-top:64px">
      <div class="dim">- id: TERM-payment</div>
      <div class="add">+ id: TERM-charge</div>
    </div>
    <p class="kicker">One file changed. Three other documents still point at the old one.</p>
  </div>"""))

# ── 2 · the silent failure ───────────────────────────────────────────────────
SLIDES.append(slide(2, """
  <div class="pad">
    <h2 class="mega">Nothing<br>breaks.</h2>
    <div class="crosses">
      <div class="x">No crash</div>
      <div class="x">No failing test</div>
      <div class="x">No review comment</div>
    </div>
    <p class="kicker">Eleven months later two meanings are in circulation, and nobody
      can trace where they diverged.</p>
  </div>""", bg=ORA))

# ── 3 · the asymmetry ────────────────────────────────────────────────────────
SLIDES.append(slide(3, """
  <div class="pad center">
    <h1 class="giant">Your code<br>has a<br><span class="hl">compiler.</span></h1>
    <h1 class="giant" style="margin-top:56px">Your product<br>model has<br><span class="hl">hope.</span></h1>
  </div>"""))

# ── 4 · what it does ─────────────────────────────────────────────────────────
SLIDES.append(slide(4, f"""
  <div class="pad">
    <span class="eyebrow">What it does</span>
    <h2>Typed artifacts,<br>beside your code.</h2>
    <div class="flow">
      <div class="node" style="background:{CRM}">glossary<br>rules<br>features</div>
      <div class="arrow">&rarr;</div>
      <div class="node" style="background:{YEL}">the gate<span class="sm">keelspec validate</span></div>
      <div class="arrow">&rarr;</div>
      <div class="node" style="background:{PAPER}">one bundle<span class="sm">byte-stable</span></div>
    </div>
    <p class="kicker">A rename that breaks three references fails the build in seconds
      — before a reviewer opens it.</p>
  </div>""", bg=BLU))

# ── 5 · the codes, in the homepage rail's own styling ────────────────────────
SLIDES.append(slide(5, f"""
  <div class="pad">
    <span class="eyebrow">Stable diagnostic codes</span>
    <h2>Findings are an API.</h2>
    <div class="codes">
      <div class="pac" style="--c:{ORA};--t:#fff"><b>PAC<br>001</b><span class="badge">required field</span></div>
      <div class="pac" style="--c:{RED};--t:{YEL}"><b>PAC<br>020</b><span class="badge">dangling reference</span></div>
      <div class="pac" style="--c:{PNK};--t:#fff"><b>PAC<br>030</b><span class="badge">enum violation</span></div>
      <div class="pac" style="--c:{YEL};--t:{INK}"><b>PAC<br>060</b><span class="badge dark">the build is stale</span></div>
    </div>
    <p class="kicker">Never renumbered. CI, dashboards and humans match on the code,
      never the prose.</p>
  </div>"""))

# ── 6 · the new bit ──────────────────────────────────────────────────────────
SLIDES.append(slide(6, f"""
  <div class="pad center">
    <span class="eyebrow">New in 0.2.0</span>
    <h1 class="giant">A workforce<br>builds it.</h1>
    <h1 class="giant" style="margin-top:44px">A <span class="hl">gate</span><br>judges it.</h1>
  </div>""", bg=INK, dark=True))

# ── 7 · the line, with the real faces ────────────────────────────────────────
SLIDES.append(slide(7, f"""
  <div class="pad">
    <span class="eyebrow">The line</span>
    <h2>Six stations, then a judge.</h2>
    <div class="stns">
      {''.join(station_card(i) for i in [0, 1, 2, 3, 4, 5, 7, 8])}
    </div>
    <p class="kicker">Open questions stop the line before design. Building the wrong
      thing correctly is the expensive failure.</p>
  </div>"""))

# ── 8 · the lenses ───────────────────────────────────────────────────────────
SLIDES.append(slide(8, f"""
  <div class="pad">
    <span class="eyebrow">ST-06 &middot; Verify</span>
    <h2>Four critics,<br>trying to refute.</h2>
    <div class="lens-grid">
      <div class="lens" style="background:{ORA}"><b>correctness</b>Find an input where it does the wrong thing.</div>
      <div class="lens" style="background:{GRN}"><b>coverage</b>Would the test still pass with the feature deleted?</div>
      <div class="lens" style="background:{BLU}"><b>security</b>Trust boundaries, authz, spend and consent.</div>
      <div class="lens" style="background:{PUR}"><b>reproduce</b>Concurrency, partial failure, retries, rollback.</div>
    </div>
    <p class="kicker">Each defaults to <b>refuted</b> unless convinced. The agent that
      built the change never grades it.</p>
  </div>""", bg=CRM))

# ── 9 · the principle ────────────────────────────────────────────────────────
SLIDES.append(slide(9, """
  <div class="pad center">
    <h1 class="giant">Agents<br><span class="hl">propose.</span></h1>
    <h1 class="giant">Gates<br><span class="hl">enforce.</span></h1>
    <h1 class="giant">A human<br><span class="hl">merges.</span></h1>
  </div>""", bg=INK, dark=True))

# ── 10 · the proof ───────────────────────────────────────────────────────────
SLIDES.append(slide(10, f"""
  <div class="pad">
    <span class="eyebrow">Proof, not a promise</span>
    <h2 class="mega">It found<br>a bug in<br>itself.</h2>
    <div class="term shadow-xl">
      <div class="tbar"><i style="background:{ORA}"></i><i style="background:{YEL}"></i><i style="background:{GRN}"></i></div>
      <div class="tbody"><span class="terr">TypeError: Object of type date<br>is not JSON serializable</span></div>
    </div>
    <p class="kicker">This blog is stored as product-as-code, so it goes through the
      same gate. Fixed in 0.2.0, with a regression test.</p>
  </div>""", bg=GRN))

# ── 11 · the CTA ─────────────────────────────────────────────────────────────
SLIDES.append(slide(11, """
  <div class="pad center">
    <h1 class="giant">Your product<br>spec,<br>compiled.</h1>
    <div class="cta mono">pip install keelspec</div>
    <div class="url">keelspec.com</div>
  </div>""", bg=YEL, footer=False))


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>KeelSpec — LinkedIn carousel</title>
<link rel="stylesheet" href="/fonts/fonts.css">
<style>
  :root{
    --ink:#191919; --yel:#fbcc00; --grn:#00b67a; --ora:#ff6b4a;
    --blu:#4a90e2; --pur:#b47cff; --crm:#fff9e6; --grid:#e5e5e5;
    --mono:'IBM Plex Mono',ui-monospace,monospace;
    --disp:'Anton','Arial Narrow',Impact,sans-serif;
    --sh:10px 10px 0 var(--ink); --sh-xl:16px 16px 0 var(--ink);
    --bd:6px solid var(--ink);
  }
  *{box-sizing:border-box;margin:0}
  body{background:#5a5a5a;font-family:'IBM Plex Sans',sans-serif;color:var(--ink)}

  .slide{
    position:relative; width:1080px; height:1350px; overflow:hidden;
    margin:0 auto 30px; display:flex; flex-direction:column;
    background-color:var(--bg);
    background-image:radial-gradient(rgba(25,25,25,.14) 4px, transparent 4px);
    background-size:52px 52px;
  }
  .slide.dark{color:#fff;background-image:radial-gradient(rgba(255,255,255,.13) 4px,transparent 4px)}
  .slide.dark .eyebrow{color:var(--yel)}
  .slide.dark .kicker{border-color:rgba(255,255,255,.35)}

  .pad{flex:1; padding:100px 88px 200px; display:flex; flex-direction:column}
  .pad.center{justify-content:center}

  .eyebrow{font-family:var(--mono);font-size:27px;font-weight:600;
    letter-spacing:.18em;text-transform:uppercase;margin-bottom:30px;display:block}
  h1,h2{font-family:var(--disp);font-weight:400;letter-spacing:.5px;line-height:.98}
  h2{font-size:88px;margin-bottom:46px}
  .mega{font-size:132px}
  .giant{font-size:124px}
  .hl{background:linear-gradient(transparent 50%, var(--yel) 50%, var(--yel) 92%, transparent 92%);
    padding-inline:.05em}
  .slide.dark .hl{color:var(--ink)}
  .kicker{margin-top:auto;font-size:33px;font-weight:600;line-height:1.38;
    border-top:7px solid var(--ink);padding-top:32px}

  .card,.term{border:var(--bd);border-radius:24px;background:#fff}
  .shadow-xl{box-shadow:var(--sh-xl)}
  .card{padding:44px 46px}
  .mono{font-family:var(--mono)}
  .card.mono{font-size:40px;line-height:1.55}
  .dim{color:#8a8a8a}
  .add{color:var(--ora);font-weight:600}

  .crosses{display:grid;gap:28px;margin-top:16px}
  .x{display:flex;align-items:center;gap:28px;font-family:var(--disp);font-size:66px;
    background:#fff;border:var(--bd);border-radius:22px;box-shadow:var(--sh);padding:24px 34px}
  .x::before{content:'\\2715';color:var(--ora);font-size:56px;font-weight:700}

  .flow{display:flex;align-items:center;gap:22px}
  .node{flex:1;min-height:250px;display:flex;flex-direction:column;justify-content:center;
    text-align:center;font-family:var(--disp);font-size:38px;line-height:1.22;
    border:var(--bd);border-radius:24px;box-shadow:var(--sh);padding:24px}
  .node .sm{display:block;font-family:var(--mono);font-size:22px;margin-top:14px;line-height:1.3}
  .arrow{font-size:60px;font-weight:700}
  .slide.dark .arrow{color:#fff}

  .codes{display:grid;grid-template-columns:1fr 1fr;gap:30px}
  .pac{position:relative;background:var(--c);border:var(--bd);border-radius:24px;
    box-shadow:var(--sh);padding:34px 32px 46px;min-height:250px}
  .pac b{font-family:var(--disp);font-size:76px;line-height:.92;color:var(--t);
    -webkit-text-stroke:3px var(--ink);paint-order:stroke fill;display:block}
  .badge{position:absolute;left:30px;bottom:-20px;background:var(--yel);color:var(--ink);
    border:4px solid var(--ink);border-radius:12px;box-shadow:4px 4px 0 var(--ink);
    padding:8px 16px;font-size:23px;font-weight:700}
  .badge.dark{background:var(--ink);color:var(--yel)}

  .stns{display:grid;grid-template-columns:1fr 1fr;gap:22px}
  .stn{position:relative;display:flex;align-items:center;gap:20px;background:#fff;
    border:var(--bd);border-radius:22px;box-shadow:var(--sh);padding:18px 22px 30px}
  .stn[data-kind=human]{background:#f2f2f2;border-style:dashed}
  .stn[data-kind=machine]{background:var(--crm)}
  .st-avatar{width:68px;height:68px;flex:none}
  .stn-t{font-family:var(--disp);font-size:35px;line-height:1.08}
  .stn-t b{display:block;font-family:var(--mono);font-size:21px;font-weight:600;
    color:#6b6b6b;letter-spacing:.08em;margin-bottom:5px}
  .chip{position:absolute;left:24px;bottom:-16px;background:var(--yel);
    border:4px solid var(--ink);border-radius:11px;box-shadow:4px 4px 0 var(--ink);
    padding:5px 13px;font-size:21px;font-weight:700}

  .lens-grid{display:grid;grid-template-columns:1fr 1fr;gap:30px}
  .lens{border:var(--bd);border-radius:24px;box-shadow:var(--sh);padding:34px 32px;
    min-height:280px;font-size:30px;font-weight:500;line-height:1.32}
  .lens b{display:block;font-family:var(--mono);font-size:40px;font-weight:600;margin-bottom:18px}

  .term{background:var(--ink);overflow:hidden;padding:0}
  .tbar{display:flex;gap:14px;padding:22px 26px;background:#2a2a2a;border-bottom:5px solid var(--ink)}
  .tbar i{width:22px;height:22px;border-radius:50%}
  .tbody{padding:40px 34px}
  .terr{font-family:var(--mono);font-size:34px;font-weight:600;color:var(--ora);line-height:1.5}

  .cta{margin-top:64px;align-self:flex-start;background:var(--ink);color:var(--yel);
    font-size:52px;padding:34px 48px;border-radius:22px;box-shadow:var(--sh-xl)}
  .url{margin-top:auto;font-family:var(--disp);font-size:70px;letter-spacing:.5px}

  .foot{position:absolute;left:88px;right:88px;bottom:56px;display:flex;
    align-items:center;justify-content:space-between}
  .fmark{display:flex;align-items:center;gap:18px;font-family:var(--disp);
    font-size:38px;letter-spacing:.3px}
  .num{font-family:var(--mono);font-size:30px;font-weight:600;opacity:.55}
  .mark{width:56px;height:56px}

  /* ── the PDF ─────────────────────────────────────────────────────────────
     Save as PDF, margins NONE, "Background graphics" ON. */
  @page{size:1080px 1350px;margin:0}
  @media print{
    body{background:#fff}
    .slide{margin:0;page-break-after:always;break-after:page}
    .slide:last-child{page-break-after:auto;break-after:auto}
    .note{display:none}
    *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  }
  .note{max-width:1080px;margin:26px auto;padding:22px 26px;background:#fff;
    border:5px solid var(--ink);border-radius:18px;font-size:19px;line-height:1.55}
  .note b{font-family:var(--disp);font-size:24px;letter-spacing:.3px}
  .note code{font-family:var(--mono);background:var(--crm);padding:2px 7px;border-radius:5px}
</style>
</head>
<body>
<div class="note">
  <b>How to post this</b><br>
  Print this page &rarr; <b>Destination:</b> Save as PDF &rarr; <b>Margins:</b> None
  &rarr; tick <b>Background graphics</b>. One 1080&times;1350 slide per page. On
  LinkedIn choose <b>Add a document</b>, upload the PDF, and title it with the hook —
  the title shows above the carousel. This page is <code>noindex</code>.
</div>
__SLIDES__
</body>
</html>
"""


def main() -> int:
    OUT.write_text(PAGE.replace("__SLIDES__", "\n".join(SLIDES)),
                   encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(OUT.parent.parent)}  ({len(SLIDES)} slides)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
