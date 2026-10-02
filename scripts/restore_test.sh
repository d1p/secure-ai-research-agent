#!/usr/bin/env bash
# Restore-verification: restore the latest dumps into a scratch DB and verify
# representative row counts. Run before declaring backups healthy.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
PGHOST="${PGHOST:-postgres}"
PGUSER="${PGUSER:-postgres}"

LATEST="$(ls -t "$BACKUP_DIR"/orchestrator-*.dump.gz 2>/dev/null | head -1 || true)"
if [ -z "$LATEST" ]; then
  echo "ERROR: no orchestrator dump found in $BACKUP_DIR" >&2
  exit 1
fi
echo "restoring: $LATEST"

SCRATCH_DB="restore_test_$$"
createdb -h "$PGHOST" -U "$PGUSER" "$SCRATCH_DB"
trap 'dropdb -h "$PGHOST" -U "$PGUSER" "$SCRATCH_DB" 2>/dev/null || true' EXIT

gunzip -c "$LATEST" | psql -h "$PGHOST" -U "$PGUSER" -d "$SCRATCH_DB" -v ON_ERROR_STOP=1

echo "representative row counts (scratch db '$SCRATCH_DB'):"
psql -h "$PGHOST" -U "$PGUSER" -d "$SCRATCH_DB" -Atc \
  "SELECT 'approvals=' || count(*) FROM orchestrator.approvals
   UNION ALL SELECT 'browser_audit=' || count(*) FROM orchestrator.browser_audit
   UNION ALL SELECT 'research_notes=' || count(*) FROM orchestrator.research_notes
   UNION ALL SELECT 'checkpoints=' || count(*) FROM orchestrator.checkpoints;"

echo "restore test OK"
