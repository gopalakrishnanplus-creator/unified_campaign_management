#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/unified_campaign_management}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SHARED_VENV_DIR="${SHARED_VENV_DIR:-/var/www/venv}"

ensure_shared_venv() {
  if [ -x "$SHARED_VENV_DIR/bin/python" ]; then
    return 0
  fi

  echo "Bootstrapping shared virtualenv at $SHARED_VENV_DIR"

  local parent_dir
  parent_dir="$(dirname "$SHARED_VENV_DIR")"

  if [ ! -d "$parent_dir" ]; then
    sudo mkdir -p "$parent_dir"
  fi

  if [ -e "$SHARED_VENV_DIR" ]; then
    sudo rm -rf "$SHARED_VENV_DIR"
  fi

  sudo mkdir -p "$SHARED_VENV_DIR"
  sudo chown -R "$(id -un)":"$(id -gn)" "$SHARED_VENV_DIR"

  "$PYTHON_BIN" -m venv "$SHARED_VENV_DIR"
}

cd "$APP_DIR"

mkdir -p "$APP_DIR/media" "$APP_DIR/staticfiles"

ensure_shared_venv

# shellcheck disable=SC1090
source "$SHARED_VENV_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

python manage.py migrate
python manage.py check
python manage.py seed_support_baseline

for pdf_path in \
  "$APP_DIR/Inclinic-FAQs - Google Sheets.pdf" \
  "$APP_DIR/PE-FAQs - Google Sheets.pdf" \
  "$APP_DIR/RFA-FAQs - Google Sheets.pdf"
do
  if [ ! -f "$pdf_path" ]; then
    echo "Missing required support PDF: $pdf_path" >&2
    exit 1
  fi
done

python manage.py import_support_pdfs --replace \
  "$APP_DIR/Inclinic-FAQs - Google Sheets.pdf" \
  "$APP_DIR/PE-FAQs - Google Sheets.pdf" \
  "$APP_DIR/RFA-FAQs - Google Sheets.pdf"

python manage.py shell <<'PY'
import csv
from pathlib import Path
from urllib.parse import urlparse

from apps.support_center.services import get_faq_combination

csv_path = Path("docs/support-widget-links.csv")
missing = []
checked = 0

with csv_path.open(newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    for row in reader:
        widget_path = urlparse(row["widget_url"]).path.strip("/")
        parts = widget_path.split("/")
        if len(parts) != 6 or parts[0] != "support" or parts[2] != "faq" or parts[5] != "widget":
            raise SystemExit(f"Unexpected widget URL format in CSV: {row['widget_url']}")
        _, user_type, _, super_slug, category_slug, _ = parts
        checked += 1
        if not get_faq_combination(user_type, super_slug, category_slug):
            missing.append(f"{user_type}/{super_slug}/{category_slug}")

print(f"Validated {checked} support widget combinations from {csv_path}.")
if missing:
    print("Missing support combinations:")
    for item in missing:
        print(f" - {item}")
    raise SystemExit(f"{len(missing)} support widget combinations are missing after deploy.")
PY

python manage.py collectstatic --noinput
