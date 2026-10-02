#!/usr/bin/env bash
# Nightly backup: all PostgreSQL databases + Open WebUI data.
# Refuses to run unless the backup destination is a real NFS mountpoint
# (i.e. /data is mounted). Retention: 7 days. Never backs up browser-profile.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
OWUI_DIR="${OWUI_DIR:-/openwebui-data}"
PGHOST="${PGHOST:-postgres}"
PGUSER="${PGUSER:-postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

# 1. Verify the destination is a mountpoint AND backed by NFS (/data).
if ! mountpoint -q "$BACKUP_DIR"; then
  echo "ERROR: $BACKUP_DIR is not a mountpoint; refusing to back up." >&2
  exit 1
fi
fstype="$(stat -f -c %T "$BACKUP_DIR" 2>/dev/null || echo unknown)"
case "$fstype" in
  nfs|nfs4) ;;
  *)
    echo "ERROR: $BACKUP_DIR is not on NFS (filesystem '$fstype'); /data is not mounted." >&2
    exit 1
    ;;
esac

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

# 2. Dump each database separately (restorable into a scratch DB).
DATABASES=("postgres" "openwebui" "litellm" "orchestrator")
for db in "${DATABASES[@]}"; do
  if psql -h "$PGHOST" -U "$PGUSER" -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1; then
    pg_dump -h "$PGHOST" -U "$PGUSER" -d "$db" --clean --if-exists \
      | gzip > "$BACKUP_DIR/${db}-${TIMESTAMP}.dump.gz"
    echo "dumped database: $db"
  else
    echo "skipping missing database: $db"
  fi
done

# 3. Open WebUI data (named volume, mounted read-only). Never browser-profile.
if [ -d "$OWUI_DIR" ] && [ -n "$(ls -A "$OWUI_DIR" 2>/dev/null)" ]; then
  tar -czf "$BACKUP_DIR/openwebui-data-${TIMESTAMP}.tar.gz" -C "$OWUI_DIR" .
  echo "backed up Open WebUI data"
fi

# 4. Retention.
find "$BACKUP_DIR" \( -name '*.dump.gz' -o -name 'openwebui-data-*.tar.gz' \) \
  -mtime +"$RETENTION_DAYS" -delete 2>/dev/null || true

echo "Backup complete at $TIMESTAMP"
