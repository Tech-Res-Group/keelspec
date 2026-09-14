# Deploying keelspec.com on Hetzner Cloud

The site is static HTML/CSS/JS with one small API container behind Caddy. Caddy
terminates TLS and issues certificates automatically. Everything runs from one
`docker compose` file on one server.

---

## 1. Which Hetzner box

**Start with a `CX23` in Falkenstein or Nuremberg — €5.49/month.**

Hetzner adjusted cloud prices on 15 June 2026. The relevant part of the lineup
(all prices **ex-VAT and excluding the primary IPv4 charge**, all with 20 TB of
traffic):

| Plan     | vCPU           | RAM   | NVMe   | €/month | Notes                             |
|----------|----------------|-------|--------|---------|-----------------------------------|
| **CX23** | 2 × Intel      | 4 GB  | 40 GB  | **5.49** | **Start here.**                  |
| CAX11    | 2 × Ampere ARM | 4 GB  | 40 GB  | 5.99    | Same specs, now *more* expensive  |
| CX33     | 4 × Intel      | 8 GB  | 80 GB  | 8.49    | Move here when a CRM lands        |
| CAX21    | 4 × Ampere ARM | 8 GB  | 80 GB  | 10.49   | —                                 |

Add roughly **€0.50–0.60/month** for the primary IPv4 address (an IPv6-only
server avoids it entirely, but then you can't reach it from IPv4-only networks —
not worth the trouble for a public marketing site).

**All-in: about €6/month, so ~€72/year.**

Two things worth knowing:

- The ARM boxes used to be the cheap option. After the June 2026 adjustment
  `CAX11` costs *more* than `CX23` for identical specs, so the old
  "always pick ARM on Hetzner" advice is now backwards. x86 is both cheaper and
  avoids any `arm64` image availability questions.
- Don't take the 2 GB plans. Postgres plus a CRM will not fit, and Hetzner lets
  you rescale CPU/RAM in place later but **disk only grows, never shrinks** — so
  the cheap starting point should be one you can grow out of, which `CX23` is.

Also worth enabling:

- **Cloud Firewall** — free. Allow inbound `22`, `80`, `443` only.
- **Backups** — +20% of the server price (≈€1.10/month). Cheap insurance for a
  box that will hold your only copy of the lead database.

### Headroom for what you want to add

Rough resident memory on a 4 GB box:

| Component                      | RAM     | Status                          |
|--------------------------------|---------|---------------------------------|
| Caddy                          | ~30 MB  | always on                       |
| Lead-capture API               | ~90 MB  | always on                       |
| Umami + Postgres (analytics)   | ~500 MB | `--profile analytics`           |
| **Subtotal**                   | ~620 MB | comfortable on CX23             |
| EspoCRM + MariaDB              | ~800 MB | still fits CX23                 |
| Twenty CRM (Postgres + Redis)  | ~1.5 GB | tight — go CX33 first           |

So: **CX23 now**, and rescale to **CX33 (€8.49)** the day you install a heavy
CRM. Rescaling is a reboot, not a migration.

---

## 2. Server setup, once

```bash
# as root on a fresh Ubuntu 24.04 image
adduser --disabled-password --gecos '' deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy

curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy

# lock down password logins
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh
```

DNS — point both records at the server's IPv4 (and AAAA at its IPv6):

```
keelspec.com.       A     <server-ip>
www.keelspec.com.   A     <server-ip>
```

Let the records propagate *before* first boot, or Caddy's certificate request
fails and retries on a backoff.

---

## 3. First deploy

```bash
ssh deploy@keelspec.com 'mkdir -p /opt/keelspec-site'

# from site/ on your machine
KEELSPEC_HOST=deploy@keelspec.com ./deploy.sh

# then, on the server, once:
cd /opt/keelspec-site
cp .env.example .env && chmod 600 .env
# fill in ACME_EMAIL, and generate the secrets:
#   openssl rand -hex 32   → ADMIN_TOKEN
#   openssl rand -hex 16   → IP_SALT
docker compose up -d
docker compose logs -f caddy      # watch the certificate get issued
```

After that, `./deploy.sh` is the whole workflow. Static edits are live on rsync
— `public/` is a read-only bind mount, so there is nothing to rebuild.

---

## 4. Adding analytics

Umami is self-hosted, cookieless, and needs no consent banner under GDPR
because it stores no personal data and sets no cookies.

```bash
# on the server
docker compose --profile analytics up -d
```

Caddy already routes `/stats/*` to it, which means the tracking script is served
from your own origin — no third-party request, and ad blockers leave it alone.
Log in at `https://keelspec.com/stats`, create the site, then add its snippet to
`public/index.html` before `</body>`:

```html
<script defer src="/stats/script.js" data-website-id="PASTE-ID-HERE"></script>
```

Lighter alternative if you'd rather not run Postgres: **GoatCounter** is a single
Go binary with SQLite, about 40 MB resident. Swap the two `umami*` services for
it and keep the same `/stats` route.

---

## 5. Adding a CRM

The lead form already posts to `POST /api/subscribe`, and everything it captures
is in one SQLite file at the `api_data` volume. Export whenever you need it:

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" https://keelspec.com/api/leads.csv -o leads.csv
```

That CSV is the import format every CRM accepts, so nothing is trapped. When you
pick one, add it as another compose service on the internal network and give it a
`handle /crm/*` block in the `Caddyfile` — same pattern as `/stats`.

- **EspoCRM** — PHP + MariaDB, ~800 MB, fits the CX23. Boring and complete.
- **Twenty** — modern, Postgres + Redis, ~1.5 GB. Rescale to CX33 first.
- **Listmonk** — if what you actually want is the newsletter rather than a CRM.
  ~150 MB, and it can consume `leads.csv` directly.

---

## 6. Loose ends

**Social preview image.** `public/og.html` is the card, already sized 1200×630.
Render it once and uncomment the two `og:image` lines in `index.html`:

```bash
npx playwright screenshot --viewport-size=1200,630 \
  http://localhost:8765/og.html public/og.png
```

**Google Fonts and GDPR.** `styles.css` pulls Anton and IBM Plex from Google's
CDN, which sends your visitors' IP addresses to Google. The privacy page says so
honestly, but the cleaner fix is to self-host: download the `woff2` files into
`public/fonts/`, replace the `@import` with local `@font-face` rules, and delete
that paragraph from `privacy.html`.

**Local preview.**

```bash
cd site/public && python -m http.server 8765
```

The signup form will fail against a plain file server — there's no `/api` — and
it degrades to a visible error message, which is the intended behaviour.
