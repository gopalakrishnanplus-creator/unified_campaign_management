#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt python-pptx >/dev/null

export REPORTING_API_USE_LIVE=false
export EXTERNAL_TICKETING_SYNC_ENABLED=false

python manage.py migrate
python manage.py seed_demo_data
python manage.py import_support_pdfs --replace \
  Inclinic-FAQsDoctorFlow.pdf \
  Inclinic-FAQsFieldRepFlow.pdf \
  PE-FAQsDoctorFlow.pdf \
  PE-FAQsPatientFlow.pdf \
  RFA-FAQsDoctorFlow.pdf \
  RFA-FAQsFieldRepFlow.pdf \
  RFA-FAQsPatientFlow.pdf

python manage.py shell -c "from apps.accounts.models import User; [u.set_password('DocsDemo!2026') or u.save(update_fields=['password']) for u in User.objects.all()]"
