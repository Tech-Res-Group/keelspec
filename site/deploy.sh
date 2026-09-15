#!/usr/bin/env bash
# Push the site to the server and reload. Run from site/ on your machine.
#
#   ./deploy.sh                 # uses $KEELSPEC_HOST, e.g. deploy@keelspec.com
#   ./deploy.sh root@1.2.3.4
#
# Static changes take effect immediately (Caddy serves them from a bind mount).
# Only api/ or compose changes need containers rebuilt.
set -euo pipefail

HOST="${1:-${KEELSPEC_HOST:-}}"
REMOTE_DIR="${REMOTE_DIR:-/opt/keelspec-site}"

if [[ -z "$HOST" ]]; then
  echo "usage: ./deploy.sh user@host   (or set KEELSPEC_HOST)" >&2
  exit 2
fi

echo "→ rebuilding and fingerprinting"
python tools/render_blog.py
python tools/render_pages.py
python tools/render_markdown.py
python tools/fingerprint_assets.py

echo "→ site structure gate"
python tools/check_site.py || { echo "refusing to deploy a broken page"; exit 1; }

echo "→ syncing to ${HOST}:${REMOTE_DIR}"
rsync -az --delete \
  --exclude '.env' \
  --exclude '.git' \
  --exclude '__pycache__' \
  ./public ./api ./Caddyfile ./docker-compose.yml ./.env.example \
  "${HOST}:${REMOTE_DIR}/"

echo "→ reloading"
# shellcheck disable=SC2029
ssh "$HOST" "cd ${REMOTE_DIR} && docker compose up -d --build && docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile"

echo "→ checking"
curl -fsS -o /dev/null -w '  / → %{http_code}\n'          "https://${SITE_DOMAIN:-keelspec.com}/"
curl -fsS -o /dev/null -w '  /api/health → %{http_code}\n' "https://${SITE_DOMAIN:-keelspec.com}/api/health"
echo "done."
