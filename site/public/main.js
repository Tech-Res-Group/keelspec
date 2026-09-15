/* KeelSpec — keelspec.com
   No dependencies. Everything degrades to a working page if this never loads. */
(function () {
  'use strict';

  /* ── mobile nav ───────────────────────────────────────────────────────── */
  var toggle = document.getElementById('navToggle');
  var links = document.getElementById('navLinks');
  if (toggle && links) {
    toggle.addEventListener('click', function () {
      var open = links.classList.toggle('open');
      toggle.setAttribute('aria-expanded', String(open));
    });
    links.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') {
        links.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });
  }

  /* ── copy-to-clipboard ────────────────────────────────────────────────── */
  document.querySelectorAll('.copy-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var src = document.querySelector(btn.dataset.copy);
      if (!src) return;
      var text = src.textContent.trim();

      var done = function () {
        var was = btn.textContent;
        btn.textContent = 'Copied';
        btn.dataset.copied = 'true';
        setTimeout(function () {
          btn.textContent = was;
          delete btn.dataset.copied;
        }, 1600);
      };

      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(done, fallback);
      } else {
        fallback();
      }

      function fallback() {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); done(); } catch (e) { /* nothing to do */ }
        document.body.removeChild(ta);
      }
    });
  });

  /* ── seamless marquee: duplicate the rail once, animate to -50% ───────── */
  var track = document.getElementById('railTrack');
  if (track && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    var originals = Array.prototype.slice.call(track.children);
    originals.forEach(function (node) {
      var clone = node.cloneNode(true);
      clone.setAttribute('aria-hidden', 'true');
      track.appendChild(clone);
    });
  }

  /* ── scroll reveal ────────────────────────────────────────────────────── */
  var targets = document.querySelectorAll('.reveal');
  if (!('IntersectionObserver' in window)) {
    targets.forEach(function (el) { el.classList.add('in'); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('in');
        io.unobserve(entry.target);
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });

    targets.forEach(function (el, i) {
      el.style.transitionDelay = (Math.min(i % 4, 3) * 60) + 'ms';
      io.observe(el);
    });
  }

  /* ── signup → lead capture API (the CRM seed) ─────────────────────────── */
  var form = document.getElementById('signupForm');
  var msg = document.getElementById('signupMsg');
  if (form && msg) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var email = form.email.value.trim();
      var honeypot = form.company.value;

      msg.className = 'msg';
      if (!email || email.indexOf('@') < 1 || email.indexOf('.', email.indexOf('@')) < 0) {
        msg.textContent = 'That address does not look right.';
        msg.classList.add('err');
        form.email.focus();
        return;
      }

      var btn = form.querySelector('button[type=submit]');
      btn.disabled = true;
      msg.textContent = 'Sending…';

      fetch('/api/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email, company: honeypot, source: 'landing' })
      })
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then(function () {
          form.reset();
          msg.textContent = "You're on the list. Nothing else required.";
          msg.classList.add('ok');
        })
        .catch(function () {
          msg.textContent = "Couldn't reach the server — try again, or watch the repo on GitHub.";
          msg.classList.add('err');
        })
        .finally(function () { btn.disabled = false; });
    });
  }


  /* ── contact form ─────────────────────────────────────────────────────── */
  var contact = document.getElementById('contactForm');
  var cmsg = document.getElementById('contactMsg');
  if (contact && cmsg) {
    contact.addEventListener('submit', function (e) {
      e.preventDefault();
      var payload = {
        name: contact.name.value.trim(),
        email: contact.email.value.trim(),
        subject: contact.subject.value,
        message: contact.message.value.trim(),
        website: contact.website.value
      };
      cmsg.className = 'msg';
      if (!payload.name || !payload.message || payload.email.indexOf('@') < 1) {
        cmsg.textContent = 'Please fill in your name, a valid email, and a message.';
        cmsg.classList.add('err');
        return;
      }
      var btn = contact.querySelector('button[type=submit]');
      btn.disabled = true;
      cmsg.textContent = 'Sending…';
      fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function () {
          contact.reset();
          cmsg.textContent = 'Thanks — we have it, and we will come back to you.';
          cmsg.classList.add('ok');
        })
        .catch(function () {
          cmsg.textContent = "Couldn't send that. Try again, or open a GitHub issue.";
          cmsg.classList.add('err');
        })
        .finally(function () { btn.disabled = false; });
    });
  }

  /* ── first-party analytics beacon ─────────────────────────────────────────
     No cookies and no stored IP; the server derives a daily-rotating hash purely
     to count uniques. Respects Do Not Track, and never blocks rendering. */
  (function () {
    if (navigator.doNotTrack === '1' || window.doNotTrack === '1') return;
    if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') return;
    var payload = JSON.stringify({
      path: location.pathname,
      referrer: document.referrer || ''
    });
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon('/api/track', new Blob([payload], { type: 'application/json' }));
      } else {
        fetch('/api/track', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload,
          keepalive: true
        }).catch(function () {});
      }
    } catch (e) { /* analytics must never break the page */ }
  })();

  /* ── footer year ──────────────────────────────────────────────────────── */
  var year = document.getElementById('year');
  if (year) year.textContent = String(new Date().getFullYear());
})();
