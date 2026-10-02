#!/usr/bin/env bash
# Reset the browser profile (clears cookies/history/localStorage) WITHOUT
# deleting the rest of the stack. Requires explicit confirmation.
set -euo pipefail

if [ "${1:-}" != "--yes" ]; then
  echo "This wipes the persistent browser profile (cookies/history/localStorage)."
  echo "Re-run with --yes to confirm."
  exit 1
fi

echo "Stopping browser container..."
docker compose stop browser || true

# The named volume is the single source of browser state; remove and recreate it.
docker volume rm "${COMPOSE_PROJECT_NAME:-ai-stack}_browser-profile" || true

echo "Restarting browser (fresh profile)..."
docker compose up -d browser
echo "browser profile reset complete"
