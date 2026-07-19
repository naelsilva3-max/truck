#!/usr/bin/env bash
# Backup diario do banco de producao. Roda na VPS via cron do usuario deploy:
#   0 3 * * * /home/deploy/app/deploy/backup_db.sh >> /home/deploy/app/backups/backup.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

# Le a config do banco pelas settings do Django (mesmo parser do .env que a
# aplicacao usa) em vez de "source .env" -- o SECRET_KEY e outras chaves
# podem conter caracteres que quebram um source direto em shell.
mapfile -t DB_INFO < <(python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'employee_truck_control.settings')
django.setup()
from django.conf import settings
db = settings.DATABASES['default']
print(db['NAME'])
print(db['USER'])
print(db['PASSWORD'])
print(db['HOST'])
print(db['PORT'])
")
DB_NAME="${DB_INFO[0]}"
DB_USER="${DB_INFO[1]}"
DB_PASSWORD="${DB_INFO[2]}"
DB_HOST="${DB_INFO[3]}"
DB_PORT="${DB_INFO[4]}"

mkdir -p backups
STAMP=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="backups/${DB_NAME}_${STAMP}.dump"

PGPASSWORD="$DB_PASSWORD" pg_dump \
  --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" \
  --format=custom --file="$DUMP_FILE" "$DB_NAME"

echo "$(date -Iseconds) backup criado: $DUMP_FILE ($(du -h "$DUMP_FILE" | cut -f1))"

# Retencao: mantem so os ultimos 14 dias de backups.
find backups -name "${DB_NAME}_*.dump" -mtime +14 -delete
