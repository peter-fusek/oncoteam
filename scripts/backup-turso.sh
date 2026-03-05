#!/usr/bin/env bash
# Backup erika-files-mcp Turso database to local SQLite file.
# Usage: ./scripts/backup-turso.sh [output_dir]
#
# Keeps last 30 backups by default. Set BACKUP_KEEP=N to change.

set -euo pipefail

DB_NAME="erika-files-mcp"
OUTPUT_DIR="${1:-$(dirname "$0")/../backups}"
BACKUP_KEEP="${BACKUP_KEEP:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="${OUTPUT_DIR}/${DB_NAME}_${TIMESTAMP}.db"

mkdir -p "$OUTPUT_DIR"

echo "Exporting ${DB_NAME} to ${OUTPUT_FILE}..."
turso db export "$DB_NAME" --output-file "$OUTPUT_FILE"

# Verify backup
ROW_COUNT=$(sqlite3 "$OUTPUT_FILE" "SELECT COUNT(*) FROM documents;" 2>/dev/null || echo "FAILED")
if [ "$ROW_COUNT" = "FAILED" ]; then
    echo "ERROR: Backup verification failed!"
    exit 1
fi
echo "Backup OK: ${ROW_COUNT} documents, $(du -h "$OUTPUT_FILE" | cut -f1) total"

# Rotate old backups (keep last N)
cd "$OUTPUT_DIR"
BACKUP_COUNT=$(ls -1 ${DB_NAME}_*.db 2>/dev/null | wc -l | tr -d ' ')
if [ "$BACKUP_COUNT" -gt "$BACKUP_KEEP" ]; then
    REMOVE_COUNT=$((BACKUP_COUNT - BACKUP_KEEP))
    echo "Rotating: removing ${REMOVE_COUNT} old backup(s)..."
    ls -1t ${DB_NAME}_*.db | tail -n "$REMOVE_COUNT" | while read -r f; do
        rm -f "$f" "${f}-wal"
        echo "  Removed $f"
    done
fi

echo "Done. Backups in ${OUTPUT_DIR}: ${BACKUP_KEEP} retained."
