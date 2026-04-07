# Unified Campaign Management

Local Django implementation of the campaign management system described in the provided diagrams and PDFs. The project includes:

- Customer support landing pages for doctors, clinic staff, brand managers, and field reps
- FAQ support pages grouped by super category, with page-specific FAQ chat widgets for each super-category and category combination
- A ticketing system with department routing, delegation, status control, notes, and attachments
- A sequential support assistant that walks through FAQs first and escalates into ticket cases when needed
- A campaign performance system with project-manager dashboards
- Live reporting API integration for the in-clinic, red flag alert, and patient education subsystems, with local fallback contracts
- Google Auth wiring through `django-allauth` plus an optional local development login
- Local setup scripts and a GitHub Actions CI/CD workflow for EC2 deployment

## Local setup

The project was initialized in this workspace with Python `3.9.6` and is configured to run on Python `3.9+`.

1. Verify Python:
   ```bash
   python3 --version
   ```
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
4. Configure environment variables:
   ```bash
   cp .env.example .env
   ```
5. Run migrations:
   ```bash
   python manage.py migrate
   ```
6. Seed demo data:
   ```bash
   python manage.py seed_demo_data
   ```
7. Import support FAQs and ticket cases from PDF sheets when needed:
   ```bash
   python manage.py import_support_pdfs --replace \
     "/Users/inditech-tech/Desktop/Inclinic-FAQs - Google Sheets.pdf" \
     "/Users/inditech-tech/Desktop/PE-FAQs - Google Sheets.pdf" \
     "/Users/inditech-tech/Desktop/RFA-FAQs - Google Sheets.pdf"
   ```
8. Start the application locally:
   ```bash
   python manage.py runserver 127.0.0.1:8000
   ```

For convenience you can also use:

```bash
bash scripts/bootstrap_local.sh
bash scripts/start_local.sh
```

## Authentication

- Primary login path: Google OAuth via `django-allauth`
- Local fallback for development: `/accounts/dev-login/`
- Project manager email: `campaignpm@inditech.co.in`

To enable real Google OAuth locally, set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`.

## Reporting feeds

By default the dashboard and `/reporting/api/<subsystem>/` use these live endpoints:

- `REPORTING_API_RED_FLAG_ALERT_URL=https://reports.inditech.co.in/reporting/api/red_flag_alert/`
- `REPORTING_API_IN_CLINIC_URL=https://reports.inditech.co.in/reporting/api/in_clinic/`
- `REPORTING_API_PATIENT_EDUCATION_URL=https://reports.inditech.co.in/reporting/api/patient_education/`
- `WORDPRESS_HELPER_URL=https://esapa.one/` for Growth Clinic webinar and certificate-course metrics

Set `REPORTING_API_USE_LIVE=false` in `.env` if you want to force the app back to local snapshot data while developing offline.
If the Growth Clinic webinar or course IDs need to be narrowed, update `WORDPRESS_GROWTH_WEBINAR_FILTERS` and `WORDPRESS_CERTIFICATE_COURSE_IDS` in `.env`.
To add more monitored system URLs in the next cycle, set `STATUS_MONITOR_EXTRA_TARGETS_JSON` in `.env` to a JSON list of objects with `system`, `label`, and `url`.

## Database

- Local development default: SQLite
- EC2 target: MySQL via `DB_ENGINE=mysql` and the `DB_*` settings in `.env`

SQLite is used by default locally so the project runs immediately without Docker or a local MySQL install. The settings already support switching to MySQL for EC2 deployment.

## Key URLs

- `/` public landing page
- `/app/` project manager dashboard
- `/app/performance/` campaign performance page
- `/ticketing/` ticketing workspace
- `/ticketing/distribution/` ticket distribution drill-down
- `/support/doctor/`
- `/support/clinic_staff/`
- `/support/brand_manager/`
- `/support/field_rep/`
- `/support/patient/`
- `/support/<role>/faq/<super_slug>/` FAQ page for one super category
- `/support/<role>/faq/<super_slug>/<category_slug>/widget/?embed=1` embeddable FAQ-only widget
- `/support/api/<role>/faq-links/` index API returning all page/widget/embed links for that role
- `/support/api/<role>/<super_slug>/<category_slug>/` combination-specific FAQ JSON
- `/support/<role>/assistant/` guided FAQ-to-ticket chatbot flow
- `/reporting/contracts/` HTML API contract view
- `/reporting/api/contracts/` JSON contract view

## CI/CD

The repository includes [`.github/workflows/ci-cd.yml](/Users/inditech-tech/Documents/CampaignManagementSystem/unified_campaign_management/.github/workflows/ci-cd.yml)` and [scripts/deploy_ec2.sh](/Users/inditech-tech/Documents/CampaignManagementSystem/unified_campaign_management/scripts/deploy_ec2.sh) for a non-container EC2 deployment flow. Configure the required GitHub secrets before enabling automatic deployment.

## Testing Guide

See [testing-guide.md](/Users/inditech-tech/Documents/CampaignManagementSystem/unified_campaign_management/docs/testing-guide.md) for a step-by-step checklist covering authentication, support flows, ticketing, dashboards, reporting APIs, and regression checks.
For external FAQ-widget integration details, see [support-widget-integration.md](/Users/inditech-tech/Documents/CampaignManagementSystem/unified_campaign_management/docs/support-widget-integration.md).
