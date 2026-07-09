#!/usr/bin/env bash
# Roda na VPS, dentro da pasta do repo, para atualizar a aplicação.
set -euo pipefail

cd "$(dirname "$0")/.."

git pull
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart gunicorn
