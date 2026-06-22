#!/bin/sh
set -e

BACKUP_DIR=${BACKUP_DIR:-/var/opt/poultry/backups}
RETENTION_DAYS=${RETENTION_DAYS:-14}
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

log() { echo "[backup] $(date -Iseconds) $*"; }

# --- Read secrets from files if provided ---
if [ -n "$PGPASSWORD_FILE" ] && [ -f "$PGPASSWORD_FILE" ]; then
    PGPASSWORD=$(cat "$PGPASSWORD_FILE")
    if [ -z "$PGPASSWORD" ]; then
        echo "Error: PGPASSWORD from $PGPASSWORD_FILE is empty" >&2
        exit 1
    fi
    export PGPASSWORD
fi

if [ -n "$INFLUX_TOKEN_FILE" ] && [ -f "$INFLUX_TOKEN_FILE" ]; then
    INFLUX_TOKEN=$(cat "$INFLUX_TOKEN_FILE")
    if [ -z "$INFLUX_TOKEN" ]; then
        echo "Error: INFLUX_TOKEN from $INFLUX_TOKEN_FILE is empty" >&2
        exit 1
    fi
    export INFLUX_TOKEN
fi

# --- Postgres ---
log "Starting Postgres backup..."
PG_FILE="$BACKUP_DIR/postgres_$DATE.sql.gz"
pg_dump -U "$PG_USER" -h "$PG_HOST" "$PG_DB" | gzip > "$PG_FILE"
log "Postgres backup saved: $PG_FILE ($(wc -c < "$PG_FILE") bytes)"

# --- InfluxDB ---
log "Starting InfluxDB backup..."
INFLUX_DIR="$BACKUP_DIR/influxdb_$DATE"
influx backup "$INFLUX_DIR" \
  --host "$INFLUX_HOST" \
  --token "$INFLUX_TOKEN" \
  --org "$INFLUX_ORG"
tar czf "$INFLUX_DIR.tar.gz" -C "$BACKUP_DIR" "influxdb_$DATE"
rm -rf "$INFLUX_DIR"
log "InfluxDB backup saved: $INFLUX_DIR.tar.gz"

# --- Media files (best-effort, optional) ---
if [ -n "$MEDIA_BACKUP_DIR" ] && [ -d "$MEDIA_BACKUP_DIR" ]; then
    log "Starting media backup..."
    MEDIA_FILE="$BACKUP_DIR/media_$DATE.tar.gz"
    tar czf "$MEDIA_FILE" -C "$(dirname "$MEDIA_BACKUP_DIR")" "$(basename "$MEDIA_BACKUP_DIR")"
    log "Media backup saved: $MEDIA_FILE ($(wc -c < "$MEDIA_FILE") bytes)"
fi

# --- Prune old backups ---
log "Pruning backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "postgres_*.sql.gz" -type f -mtime "+$RETENTION_DAYS" -exec rm {} \;
find "$BACKUP_DIR" -name "influxdb_*.tar.gz" -type f -mtime "+$RETENTION_DAYS" -exec rm {} \;
find "$BACKUP_DIR" -name "media_*.tar.gz" -type f -mtime "+$RETENTION_DAYS" -exec rm {} \;

log "Backup complete."
