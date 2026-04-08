#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/unified_campaign_management}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SERVICE_NAME="${SERVICE_NAME:-campaign-management}"

cd "$APP_DIR"

if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

python manage.py migrate

# Import support PDFs (from repo root)
python manage.py import_support_pdfs --replace \
  "$APP_DIR/Inclinic-FAQs - Google Sheets.pdf" \
  "$APP_DIR/PE-FAQs - Google Sheets.pdf" \
  "$APP_DIR/RFA-FAQs - Google Sheets.pdf"

python manage.py collectstatic --noinput

if command -v systemctl >/dev/null 2>&1; then
  sudo systemctl restart "$SERVICE_NAME"
fi
