"""Render the standing pages (legal, company, contact) with the shared chrome.

Keeping these in one generator means the nav and footer can never drift between
pages -- which is the same argument the product makes, applied to its own site.

    python tools/render_pages.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from render_blog import page  # noqa: E402  (shared chrome: nav, footer, head)
from pdlc_page import BODY as PDLC_BODY  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent / "public"
UPDATED = "23 August 2026"

PAGES: dict[str, tuple[str, str, str]] = {}


def prose(title: str, body: str, updated: bool = True) -> str:
    stamp = f'<p class="updated">Last updated {UPDATED}</p>' if updated else ""
    return f"""<main class="section">
  <div class="wrap prose">
    {body.replace("<!--STAMP-->", stamp)}
    <p style="margin-top:2.6rem"><a class="btn" href="/">Back to the front page</a></p>
  </div>
</main>"""


# ── terms of use ─────────────────────────────────────────────────────────────
PAGES["terms.html"] = (
    "Terms of Use — KeelSpec",
    "The terms governing use of keelspec.com and the KeelSpec software.",
    prose("Terms", """
<span class="eyebrow">Legal</span>
<h1>Terms of use</h1>
<!--STAMP-->

<p>These terms govern your use of <strong>keelspec.com</strong> (the &ldquo;site&rdquo;) and any
services offered through it. The KeelSpec software itself is licensed separately &mdash; see
<a href="#software">The software</a> below.</p>

<h2>Using the site</h2>
<p>You may read, link to, and quote this site freely. You may not attempt to gain unauthorised
access to it, interfere with its operation, or use automated systems in a way that degrades
service for others. Reasonable crawling that respects
<a href="/robots.txt">robots.txt</a> is welcome.</p>

<h2 id="software">The software</h2>
<p>KeelSpec is distributed under the <strong>GNU Lesser General Public License, version 3 or
later</strong>. That licence &mdash; not this page &mdash; governs your rights to use, modify and
redistribute the software. In particular, importing KeelSpec as a library or running it in your
CI places no obligation on your own project beyond the notice. The full text ships with the package and is
available in the <a href="https://github.com/Tech-Res-Group/keelspec/blob/main/LICENSE">repository</a>.</p>
<p>The software is provided <strong>as is, without warranty of any kind</strong>, as set out in
the licence. Nothing on this site modifies or expands that licence.</p>

<h2>Your content</h2>
<p>If you send us feedback, bug reports, or feature suggestions, we may act on them without
obligation or compensation. Do not send us anything you consider confidential. Contributions to
the source repository are governed by the project licence.</p>

<h2>Email and messages</h2>
<p>If you subscribe to the newsletter you consent to receiving it at the address you provide.
Every message carries a one-click unsubscribe link. SMS messaging, if you opt in separately, is
governed by the <a href="/sms-opt-in.html">SMS opt-in terms</a>.</p>

<h2>Availability</h2>
<p>The site is offered on a best-effort basis. We may change, suspend or discontinue any part of
it at any time. We do not guarantee uninterrupted availability, and we are not liable for losses
arising from downtime.</p>

<h2>Limitation of liability</h2>
<p>To the fullest extent permitted by law, we are not liable for any indirect, incidental,
consequential or punitive damages arising from your use of the site or the software, including
lost profits, lost data, or business interruption &mdash; even if advised of the possibility.
Nothing here excludes liability that cannot lawfully be excluded.</p>

<h2>Third-party links</h2>
<p>The site links to third-party services including GitHub and PyPI. We do not control them and
are not responsible for their content or practices.</p>

<h2>Changes</h2>
<p>We may revise these terms. Material changes will be reflected in the &ldquo;last updated&rdquo;
date above. Continuing to use the site after a change constitutes acceptance.</p>

<h2>Contact</h2>
<p>Questions about these terms: <a href="/contact.html">contact us</a>, or open an issue on
<a href="https://github.com/Tech-Res-Group/keelspec/issues">GitHub</a>.</p>
"""))

# ── SMS opt-in ───────────────────────────────────────────────────────────────
PAGES["sms-opt-in.html"] = (
    "SMS Opt-In — KeelSpec",
    "How SMS messaging from KeelSpec works: consent, frequency, cost, and how to stop.",
    prose("SMS", """
<span class="eyebrow">Messaging</span>
<h1>SMS opt-in</h1>
<!--STAMP-->

<blockquote>We do not currently send SMS messages. This page sets out the terms that will apply
if and when we do, so that consent is never collected without them being available first.</blockquote>

<h2>What you are consenting to</h2>
<p>If you provide your mobile number and tick the SMS consent box, you agree to receive text
messages from KeelSpec about product updates, release announcements, and service notifications
relevant to your account.</p>
<p>Consent to receive SMS is <strong>never a condition of purchase</strong> and is never required
to use KeelSpec, download the software, or subscribe to the email newsletter.</p>

<h2>Message frequency</h2>
<p>Message frequency varies. We expect no more than <strong>four messages per month</strong>.
Service notifications (for example, a security advisory affecting a release you use) may be sent
outside that cadence.</p>

<h2>Cost</h2>
<p><strong>Message and data rates may apply.</strong> These are set by your mobile carrier, not by
us. Check your plan if you are unsure.</p>

<h2>How to stop</h2>
<p>Reply <strong>STOP</strong> to any message to unsubscribe immediately. You will receive one
final confirmation and then nothing further. You can also
<a href="/contact.html">contact us</a> to be removed.</p>
<p>Reply <strong>HELP</strong> to any message for assistance, or reach us through the
<a href="/contact.html">contact page</a>.</p>

<h2>Carriers</h2>
<p>Carriers are not liable for delayed or undelivered messages.</p>

<h2>Eligibility</h2>
<p>You must be at least 18 and the account holder, or have the account holder's permission, for
the mobile number you provide.</p>

<h2>Your data</h2>
<p>Your mobile number is used solely to deliver the messages described above. It is not sold,
rented, or shared with third parties for their marketing. Mobile opt-in data and consent are never
shared with anyone for marketing purposes. See our <a href="/privacy.html">privacy policy</a> for
how we handle personal data and how to request deletion.</p>

<h2>Changes</h2>
<p>We may update these terms; the date above reflects the current version. Material changes
affecting active subscribers will be notified by message before taking effect.</p>
"""))

# ── who we are ───────────────────────────────────────────────────────────────
PAGES["who-we-are.html"] = (
    "Who We Are — KeelSpec",
    "The people behind KeelSpec and the payments platform it was extracted from.",
    prose("Who we are", """
<span class="eyebrow">Company</span>
<h1>Who we are</h1>

<p class="lede">KeelSpec was not built as a product. It was built because a payments platform
needed its product intent to stop rotting, and the thing that fixed it turned out to be worth
extracting.</p>

<div class="person">
  <div class="person-avatar">CW</div>
  <div>
    <h2>Colin Wynd</h2>
    <div class="role">Founder &middot; author of KeelSpec</div>
    <p style="margin-top:0.9rem">Built the product-as-code engine inside the pharthing /
    KibiPay payments platform, where it grew to cover 39 features, a concept catalogue and a
    rulebook, and became the platform's sole product CI gate. Extracted it as KeelSpec so
    other teams could use it &mdash; verified by a byte-identical parity test proving nothing
    was lost on the way out.</p>
    <p>Every design decision in the tool came from something going wrong first: the staleness
    gate because specs silently diverged from builds, typed references because renames quietly
    orphaned business rules, plugins because a real migration cannot afford to drop any of its
    bespoke checks.</p>
    <p>He writes about software and other preoccupations at
    <a href="https://tarvit.com">tarvit.com</a>.</p>
    <div class="person-links">
      <a href="https://www.linkedin.com/in/colinwynd">LinkedIn</a>
      <a href="https://tarvit.com">tarvit.com</a>
      <a href="https://github.com/tarvitave">GitHub</a>
      <a href="/contact.html">Contact</a>
    </div>
  </div>
</div>

<h2>Where it came from</h2>
<p>The pharthing / KibiPay payments platform runs <code>keelspec validate</code> as its only
product gate, via a plugin that adds domain-specific checks. Every feature in the tool exists
because something went wrong without it: the staleness gate because specs silently diverged from
builds, typed references because renames quietly orphaned business rules, plugins because a real
migration cannot afford to lose any of its bespoke checks.</p>
<p>You can read more about what survived contact with production in
<a href="/blog/payments-case-study.html">what we learned running this in payments</a>.</p>

<h2>What we believe</h2>
<ul>
  <li><strong>Gates check facts, not taste.</strong> A validator that argues about judgement gets
    bypassed, and a bypassed gate is worse than none.</li>
  <li><strong>Codes are an API.</strong> Diagnostic numbers are never renumbered, because
    everything downstream depends on them.</li>
  <li><strong>Ship the smallest thing that closes the loop.</strong> Most of the value is two
    checks: do references resolve, and does the build match its sources.</li>
</ul>

<h2>Get in touch</h2>
<p>Bugs and feature requests belong on
<a href="https://github.com/Tech-Res-Group/keelspec/issues">GitHub</a>, where they are public and
tracked. Anything else, use the <a href="/contact.html">contact page</a>.</p>
""", updated=False))

# ── contact ──────────────────────────────────────────────────────────────────
PAGES["contact.html"] = (
    "Contact Us — KeelSpec",
    "Get in touch with the KeelSpec team about the software, licensing, or anything else.",
    f"""<main class="section">
  <div class="wrap prose">
    <span class="eyebrow">Contact</span>
    <h1>Contact us</h1>
    <p class="lede" style="margin-top:1.1rem">Bugs and feature requests are best raised on GitHub,
      where they are public and tracked. For anything else, this reaches us directly.</p>

    <form class="signup" id="contactForm" style="max-width:none;margin-top:2.4rem" novalidate>
      <label class="hp" for="website">Website (leave blank)</label>
      <input class="hp" type="text" id="website" name="website" tabindex="-1" autocomplete="off">

      <div style="display:grid;gap:1rem">
        <div>
          <label for="cname" style="display:block;font-weight:600;margin-bottom:0.4rem">Your name</label>
          <input type="text" id="cname" name="name" required autocomplete="name"
                 style="width:100%;font:inherit;padding:0.8rem 1rem;background:var(--paper);
                        border:var(--bd);border-radius:10px;box-shadow:var(--sh-sm)">
        </div>
        <div>
          <label for="cemail" style="display:block;font-weight:600;margin-bottom:0.4rem">Email address</label>
          <input type="email" id="cemail" name="email" required autocomplete="email"
                 style="width:100%;font:inherit;padding:0.8rem 1rem;background:var(--paper);
                        border:var(--bd);border-radius:10px;box-shadow:var(--sh-sm)">
        </div>
        <div>
          <label for="csubject" style="display:block;font-weight:600;margin-bottom:0.4rem">Subject</label>
          <select id="csubject" name="subject"
                  style="width:100%;font:inherit;padding:0.8rem 1rem;background:var(--paper);
                         border:var(--bd);border-radius:10px;box-shadow:var(--sh-sm)">
            <option>General question</option>
            <option>Licensing</option>
            <option>Using KeelSpec at scale</option>
            <option>Press or speaking</option>
            <option>Something else</option>
          </select>
        </div>
        <div>
          <label for="cmessage" style="display:block;font-weight:600;margin-bottom:0.4rem">Message</label>
          <textarea id="cmessage" name="message" rows="7" required
                    style="width:100%;font:inherit;padding:0.8rem 1rem;background:var(--paper);
                           border:var(--bd);border-radius:10px;box-shadow:var(--sh-sm);resize:vertical"></textarea>
        </div>
        <div>
          <button class="btn btn-primary btn-lg" type="submit">Send message</button>
        </div>
      </div>
      <p class="msg" id="contactMsg" role="status" aria-live="polite"></p>
    </form>

    <h2>Where we are</h2>
    <p itemscope itemtype="https://schema.org/PostalAddress">
      <span itemprop="streetAddress">64 Walnute Ave, Suite 405</span><br>
      <span itemprop="addressLocality">Clark</span>,
      <span itemprop="addressRegion">NJ</span>
      <span itemprop="postalCode">07066</span><br>
      <span itemprop="addressCountry">United States</span>
    </p>

    <h2>Other ways</h2>
    <ul>
      <li><strong>Bugs and features</strong> &mdash;
        <a href="https://github.com/Tech-Res-Group/keelspec/issues">GitHub issues</a></li>
      <li><strong>Source and releases</strong> &mdash;
        <a href="https://github.com/Tech-Res-Group/keelspec">github.com/Tech-Res-Group/keelspec</a></li>
      <li><strong>Packages</strong> &mdash;
        <a href="https://pypi.org/project/keelspec/">PyPI</a></li>
      <li><strong>Email</strong> &mdash; marketing@keelspec.com</li>
    </ul>

    <h2>Data</h2>
    <p>What you send here is used to answer you and nothing else. See the
      <a href="/privacy.html">privacy policy</a>.</p>

    <p style="margin-top:2.6rem"><a class="btn" href="/">Back to the front page</a></p>
  </div>
</main>""")


PAGES["lifecycle.html"] = (
    "One lifecycle, not two — KeelSpec",
    "PDLC and SDLC in one repository, behind one gate, with a reproducible audit trail. "
    "Checks on every edge where product intent fans out into code, tests and docs.",
    PDLC_BODY)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for filename, (title, desc, body) in PAGES.items():
        (OUT / filename).write_text(
            page(title, desc, body, "/" + filename),
            encoding="utf-8", newline="\n")
        print(f"  wrote public/{filename}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
