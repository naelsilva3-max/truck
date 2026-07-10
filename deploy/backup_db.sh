#!/usr/bin/env bash
# Backup diario do banco de producao. Roda na VPS via cron do usuario deploy:
#   0 3 * * * /home/deploy/app/deploy/backup_db.sh >> /home/deploy/app/backups/backup.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/.."
set -a
source .env
set +a

mkdir -p backups
STAMP=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="backups/${DB_NAME}_${STAMP}.dump"

PGPASSWORD="$DB_PASSWORD" pg_dump \
  --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" \
  --format=custom --file="$DUMP_FILE" "$DB_NAME"

echo "$(date -Iseconds) backup criado: $DUMP_FILE ($(du -h "$DUMP_FILE" | cut -f1))"

# Retencao: mantem so os ultimos 14 dias de backups.
find backups -name "${DB_NAME}_*.dump" -mtime +14 -delete
