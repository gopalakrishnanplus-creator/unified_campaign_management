#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/unified_campaign_management}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SHARED_VENV_DIR="${SHARED_VENV_DIR:-/var/www/venv}"
SECRETS_ENV_PATH="${SECRETS_ENV_PATH:-/var/www/secrets/.env}"
SECRETS_ENV_GROUP="${SECRETS_ENV_GROUP:-$(id -gn)}"

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

ensure_secrets_env_permissions() {
  local secrets_dir
  secrets_dir="$(dirname "$SECRETS_ENV_PATH")"

  if [ ! -d "$secrets_dir" ]; then
    sudo mkdir -p "$secrets_dir"
  fi

  sudo chgrp "$SECRETS_ENV_GROUP" "$secrets_dir" || true
  sudo chmod 750 "$secrets_dir" || true

  if [ -f "$SECRETS_ENV_PATH" ]; then
    sudo chgrp "$SECRETS_ENV_GROUP" "$SECRETS_ENV_PATH" || true
    sudo chmod 640 "$SECRETS_ENV_PATH" || true
  fi

  if [ -e "$SECRETS_ENV_PATH" ] && [ ! -r "$SECRETS_ENV_PATH" ]; then
    echo "Secrets env file exists but is still unreadable: $SECRETS_ENV_PATH" >&2
    exit 1
  fi
}

all_files_exist() {
  local file_path
  for file_path in "$@"; do
    if [ ! -f "$file_path" ]; then
      return 1
    fi
  done
  return 0
}

cd "$APP_DIR"

mkdir -p "$APP_DIR/media" "$APP_DIR/staticfiles"

ensure_shared_venv
ensure_secrets_env_permissions

# shellcheck disable=SC1090
source "$SHARED_VENV_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

python manage.py migrate
python manage.py check
python manage.py seed_support_baseline

FLOW_SUPPORT_PDFS=(
  "$APP_DIR/static/support-pdfs/in-clinic-flow1-doctor-faqs.pdf"
  "$APP_DIR/static/support-pdfs/in-clinic-flow2-field-rep-faqs.pdf"
  "$APP_DIR/static/support-pdfs/patient-education-flow1-doctor-faqs.pdf"
  "$APP_DIR/static/support-pdfs/patient-education-flow2-patient-faqs.pdf"
  "$APP_DIR/static/support-pdfs/red-flag-alert-flow1-doctor-faqs.pdf"
  "$APP_DIR/static/support-pdfs/red-flag-alert-flow2-field-rep-faqs.pdf"
  "$APP_DIR/static/support-pdfs/red-flag-alert-flow3-patient-faqs.pdf"
  "$APP_DIR/static/support-pdfs/red-flag-alert-flow4-publisher-faqs.pdf"
  "$APP_DIR/static/support-pdfs/red-flag-alert-flow5-brand-manager-faqs.pdf"
  "$APP_DIR/static/support-pdfs/saplaicme-expert-webinar-flow-faqs.pdf"
  "$APP_DIR/static/support-pdfs/saplaicme-student-ai-cme-flow-faqs.pdf"
  "$APP_DIR/static/support-pdfs/saplaicme-student-lecture-flow-faqs.pdf"
  "$APP_DIR/static/support-pdfs/saplaicme-student-webinar-flow-faqs.pdf"
)

LEGACY_SUPPORT_PDFS=(
  "$APP_DIR/Inclinic-FAQs - Google Sheets.pdf"
  "$APP_DIR/PE-FAQs - Google Sheets.pdf"
  "$APP_DIR/RFA-FAQs - Google Sheets.pdf"
)

SUPPORT_MODE=""
SUPPORT_PDFS=()

if all_files_exist "${FLOW_SUPPORT_PDFS[@]}"; then
  SUPPORT_MODE="flow"
  SUPPORT_PDFS=("${FLOW_SUPPORT_PDFS[@]}")
  echo "Using flow-wise support PDFs from static/support-pdfs."
elif all_files_exist "${LEGACY_SUPPORT_PDFS[@]}"; then
  SUPPORT_MODE="legacy"
  SUPPORT_PDFS=("${LEGACY_SUPPORT_PDFS[@]}")
  echo "Using legacy combined support PDFs."
else
  echo "Missing required support PDFs." >&2
  echo "Checked flow-wise set:" >&2
  for pdf_path in "${FLOW_SUPPORT_PDFS[@]}"; do
    if [ -f "$pdf_path" ]; then
      echo "  OK: $pdf_path" >&2
    else
      echo "  MISSING: $pdf_path" >&2
    fi
  done

  echo "Checked legacy set:" >&2
  for pdf_path in "${LEGACY_SUPPORT_PDFS[@]}"; do
    if [ -f "$pdf_path" ]; then
      echo "  OK: $pdf_path" >&2
    else
      echo "  MISSING: $pdf_path" >&2
    fi
  done
  exit 1
fi

echo "Importing support PDFs:"
for pdf_path in "${SUPPORT_PDFS[@]}"; do
  echo " - $pdf_path"
done

python manage.py import_support_pdfs --replace "${SUPPORT_PDFS[@]}"

if [ "$SUPPORT_MODE" = "flow" ]; then
  if python manage.py help export_support_widget_links >/dev/null 2>&1; then
    python manage.py export_support_widget_links --base-url https://help.cpdinclinic.co.in

    python manage.py shell <<'PY'
import csv
from pathlib import Path
from urllib.parse import urlparse

from apps.support_center.services import get_faq_page

csv_path = Path("docs/support-widget-page-links.csv")
missing = []
checked = 0

with csv_path.open(newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    for row in reader:
        widget_path = urlparse(row["widget_url"]).path.strip("/")
        parts = widget_path.split("/")
        if len(parts) != 6 or parts[0] != "support" or parts[2] != "faq" or parts[3] != "page" or parts[5] != "widget":
            raise SystemExit(f"Unexpected page widget URL format in CSV: {row['widget_url']}")
        _, user_type, _, _, page_slug, _ = parts
        checked += 1
        if not get_faq_page(user_type, page_slug):
            missing.append(f"{user_type}/{page_slug}")

print(f"Validated {checked} page-wise support widget links from {csv_path}.")
if missing:
    print("Missing support pages:")
    for item in missing:
        print(f" - {item}")
    raise SystemExit(f"{len(missing)} page-wise support widget links are missing after deploy.")
PY
  else
    echo "Warning: export_support_widget_links command is not available; skipping page-wise link export/validation." >&2
  fi
else
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
fi

python manage.py collectstatic --noinput
