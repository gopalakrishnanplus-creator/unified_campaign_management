#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from flow_definitions import ASSETS_DIR, BASE_URL


ROOT = Path(__file__).resolve().parents[2]
ASSETS_ROOT = ROOT / ASSETS_DIR
PWCLI = Path(os.environ.get("PWCLI", Path.home() / ".codex/skills/playwright/scripts/playwright_cli.sh"))

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from apps.support_center.models import SupportRequest  # noqa: E402


def js(value: str) -> str:
    return json.dumps(value)


class PlaywrightSession:
    def __init__(self, name: str):
        self.name = name

    def _base(self) -> list[str]:
        return [str(PWCLI), f"-s={self.name}"]

    def open(self) -> None:
        run([str(PWCLI), "open", "about:blank", "--session", self.name])

    def close(self) -> None:
        try:
            subprocess.run(self._base() + ["close"], check=False, text=True, timeout=5)
        except subprocess.TimeoutExpired:
            pass

    def run_code(self, code: str) -> None:
        run(self._base() + ["run-code", f"async (page) => {{ {code} }}"])


def run(cmd: list[str]) -> str:
    subprocess.run(cmd, check=True, text=True)
    return ""


def ensure_assets() -> None:
    ASSETS_ROOT.mkdir(parents=True, exist_ok=True)
    for png in ASSETS_ROOT.rglob("*.png"):
        png.unlink()


def asset_path(workflow_slug: str, filename: str) -> Path:
    directory = ASSETS_ROOT / workflow_slug
    directory.mkdir(parents=True, exist_ok=True)
    return directory / filename


def copy_asset(source: Path, workflow_slug: str, filename: str) -> None:
    target = asset_path(workflow_slug, filename)
    shutil.copy2(source, target)


def basic_capture(session: PlaywrightSession, url: str, target: Path, *, viewport=(1680, 1100), scroll_y: int | None = None, selector: str | None = None, locator_only: bool = False) -> None:
    code = [
        f"await page.setViewportSize({{ width: {viewport[0]}, height: {viewport[1]} }});",
        f"await page.goto({js(url)}, {{ waitUntil: 'networkidle' }});",
        "await page.waitForTimeout(350);",
    ]
    if scroll_y is not None:
        code.append(f"await page.evaluate(() => window.scrollTo(0, {scroll_y}));")
        code.append("await page.waitForTimeout(250);")
    if selector:
        code.append(f"await page.locator({js(selector)}).first().scrollIntoViewIfNeeded();")
        code.append("await page.waitForTimeout(250);")
        if locator_only:
            code.append(f"await page.locator({js(selector)}).first().screenshot({{ path: {js(str(target))} }});")
        else:
            code.append(f"await page.screenshot({{ path: {js(str(target))} }});")
    else:
        code.append(f"await page.screenshot({{ path: {js(str(target))} }});")
    session.run_code(" ".join(code))


def login_pm(session: PlaywrightSession) -> None:
    session.run_code(
        f"""
        await page.setViewportSize({{ width: 1680, height: 1100 }});
        await page.goto({js(BASE_URL + '/accounts/dev-login/')}, {{ waitUntil: 'networkidle' }});
        await page.waitForTimeout(450);
        """
    )


def login_owner(session: PlaywrightSession, email: str, password: str) -> None:
    session.run_code(
        f"""
        await page.setViewportSize({{ width: 1680, height: 1100 }});
        await page.goto({js(BASE_URL + '/admin/login/')}, {{ waitUntil: 'networkidle' }});
        await page.fill('input[name="username"]', {js(email)});
        await page.fill('input[name="password"]', {js(password)});
        await Promise.all([
            page.waitForNavigation({{ waitUntil: 'networkidle' }}),
            page.locator('input[type="submit"], button:has-text("Log in")').click(),
        ]);
        await page.goto({js(BASE_URL + '/ticketing/')}, {{ waitUntil: 'networkidle' }});
        await page.waitForTimeout(350);
        """
    )


def capture_public_flows(public: PlaywrightSession, run_tag: str) -> tuple[str, int]:
    home = asset_path("platform-overview-and-role-map", "01-homepage.png")
    basic_capture(public, BASE_URL + "/", home)

    doctor_landing = asset_path("doctor-self-service-support", "01-doctor-support-landing.png")
    basic_capture(public, BASE_URL + "/support/doctor/", doctor_landing)
    copy_asset(doctor_landing, "platform-overview-and-role-map", "03-doctor-support-landing.png")

    field_rep_landing = asset_path("field-rep-self-service-support", "01-field-rep-landing.png")
    basic_capture(public, BASE_URL + "/support/field_rep/", field_rep_landing)
    copy_asset(field_rep_landing, "platform-overview-and-role-map", "04-field-rep-support-landing.png")

    basic_capture(
        public,
        BASE_URL + "/support/doctor/faq/page/in-clinic-flow1-doctor-doctor-verification-page/",
        asset_path("doctor-self-service-support", "02-doctor-faq-page.png"),
    )
    basic_capture(
        public,
        BASE_URL + "/support/doctor/faq/page/in-clinic-flow1-doctor-doctor-verification-page/widget/?embed=1",
        asset_path("doctor-self-service-support", "04-doctor-widget.png"),
        viewport=(1400, 1080),
    )

    basic_capture(
        public,
        BASE_URL + "/support/clinic_staff/",
        asset_path("clinic-staff-self-service-support", "01-clinic-staff-landing.png"),
    )
    basic_capture(
        public,
        BASE_URL + "/support/clinic_staff/faq/page/customer-support-sharing-activation-page/",
        asset_path("clinic-staff-self-service-support", "02-clinic-staff-faq-page.png"),
    )
    basic_capture(
        public,
        BASE_URL + "/support/clinic_staff/",
        asset_path("clinic-staff-self-service-support", "03-clinic-staff-free-text-form.png"),
        scroll_y=980,
    )

    basic_capture(
        public,
        BASE_URL + "/support/brand_manager/",
        asset_path("brand-manager-self-service-support", "01-brand-manager-landing.png"),
    )
    basic_capture(
        public,
        BASE_URL + "/support/brand_manager/faq/page/customer-support-authentication-page/",
        asset_path("brand-manager-self-service-support", "02-brand-manager-faq-page.png"),
    )
    basic_capture(
        public,
        BASE_URL + "/support/brand_manager/",
        asset_path("brand-manager-self-service-support", "03-brand-manager-free-text-form.png"),
        scroll_y=960,
    )

    basic_capture(
        public,
        BASE_URL + "/support/field_rep/faq/page/in-clinic-flow2-fieldrep-field-rep-sharing-page/",
        asset_path("field-rep-self-service-support", "02-field-rep-faq-page.png"),
    )
    basic_capture(
        public,
        BASE_URL + "/support/field_rep/faq/page/in-clinic-flow2-fieldrep-field-rep-sharing-page/widget/?embed=1",
        asset_path("field-rep-self-service-support", "03-field-rep-widget.png"),
        viewport=(1400, 1080),
    )
    basic_capture(
        public,
        BASE_URL + "/support/field_rep/",
        asset_path("field-rep-self-service-support", "04-field-rep-free-text-form.png"),
        scroll_y=1120,
    )

    basic_capture(
        public,
        BASE_URL + "/support/patient/",
        asset_path("patient-self-service-support", "01-patient-landing.png"),
    )
    basic_capture(
        public,
        BASE_URL + "/support/patient/faq/page/patient-education-flow2-patient-patient-page/",
        asset_path("patient-self-service-support", "02-patient-faq-page.png"),
    )
    basic_capture(
        public,
        BASE_URL + "/support/patient/faq/page/patient-education-flow2-patient-patient-page/widget/?embed=1",
        asset_path("patient-self-service-support", "03-patient-widget.png"),
        viewport=(1400, 1080),
    )
    basic_capture(
        public,
        BASE_URL + "/support/patient/",
        asset_path("patient-self-service-support", "04-patient-free-text-form.png"),
        scroll_y=940,
    )

    issue_text = f"Training capture {run_tag}: verification screen accepts the number, but the confirmation state never loads after tapping Verify & Access Content."
    public.run_code(
        f"""
        await page.setViewportSize({{ width: 1680, height: 1100 }});
        await page.goto({js(BASE_URL + '/support/doctor/assistant/')}, {{ waitUntil: 'networkidle' }});
        await page.locator('button:has-text("In-clinic")').click();
        await page.waitForTimeout(200);
        await page.locator('button:has-text("Flow1 / Doctor")').click();
        await page.waitForTimeout(200);
        await page.locator('button:has-text("Doctor Number Verification Screen")').click();
        await page.waitForTimeout(300);
        await page.screenshot({{ path: {js(str(asset_path('doctor-self-service-support', '03-doctor-assistant-question.png')))} }});
        await page.locator('label:has-text("Other")').click();
        await page.waitForTimeout(350);
        await page.fill('input[name="requester_name"]', 'Dr Priya Raman');
        await page.fill('input[name="requester_number"]', '9876543210');
        await page.fill('input[name="requester_email"]', 'doctor.demo@example.com');
        await page.fill('textarea[name="free_text"]', {js(issue_text)});
        await page.screenshot({{ path: {js(str(asset_path('project-manager-review-other-submissions', '01-doctor-assistant-other-form.png')))} }});
        await Promise.all([
            page.waitForURL(/\\/support\\/doctor\\/request\\/\\d+\\/success\\//),
            page.locator('button:has-text("Raise Query")').click(),
        ]);
        await page.waitForTimeout(350);
        await page.screenshot({{ path: {js(str(asset_path('project-manager-review-other-submissions', '02-doctor-request-success.png')))} }});
        """
    )

    request_id = (
        SupportRequest.objects.filter(free_text=issue_text)
        .order_by("-pk")
        .values_list("pk", flat=True)
        .first()
    )
    if not request_id:
        raise RuntimeError("Unable to locate the support request created during capture.")

    return issue_text, int(request_id)


def capture_pm_flows(pm: PlaywrightSession, run_tag: str, issue_text: str, request_id: int) -> None:
    dashboard_overview = asset_path("project-manager-dashboard-and-triage", "01-dashboard-overview.png")
    basic_capture(pm, BASE_URL + "/app/", dashboard_overview)
    copy_asset(dashboard_overview, "platform-overview-and-role-map", "02-project-manager-dashboard.png")

    basic_capture(
        pm,
        BASE_URL + "/app/",
        asset_path("project-manager-dashboard-and-triage", "02-dashboard-operational-details.png"),
        scroll_y=420,
    )
    basic_capture(
        pm,
        BASE_URL + "/app/",
        asset_path("project-manager-dashboard-and-triage", "04-dashboard-high-priority-queue.png"),
        scroll_y=920,
    )
    pending_review = asset_path("project-manager-dashboard-and-triage", "03-dashboard-pending-issues.png")
    basic_capture(pm, BASE_URL + "/app/", pending_review, scroll_y=1320)
    copy_asset(pending_review, "project-manager-review-other-submissions", "03-pm-pending-review.png")

    pm.run_code(
        f"""
        await page.setViewportSize({{ width: 1680, height: 1100 }});
        await page.goto({js(BASE_URL + f'/support/requests/{request_id}/raise-ticket/')}, {{ waitUntil: 'networkidle' }});
        await page.waitForTimeout(350);
        await page.screenshot({{ path: {js(str(asset_path('project-manager-review-other-submissions', '04-raise-ticket-form.png')))} }});
        await page.locator('select[name="department"]').selectOption({{ label: 'Campaign Operations - Auto route to Clinical Operations Lead' }});
        await page.locator('select[name="campaign"]').selectOption({{ label: 'CardioPlus Unified Care' }});
        await page.locator('select[name="priority"]').selectOption({{ label: 'High' }});
        await Promise.all([
            page.waitForURL(/\\/ticketing\\/\\d+\\//),
            page.locator('button:has-text("Create synced ticket")').click(),
        ]);
        await page.waitForTimeout(350);
        await page.screenshot({{ path: {js(str(asset_path('project-manager-review-other-submissions', '05-raised-ticket-detail.png')))} }});
        """
    )

    manual_title = f"Training Demo Manual Ticket {run_tag}"
    pm.run_code(
        f"""
        await page.setViewportSize({{ width: 1680, height: 1100 }});
        await page.goto({js(BASE_URL + '/ticketing/new/')}, {{ waitUntil: 'networkidle' }});
        await page.waitForTimeout(300);
        await page.screenshot({{ path: {js(str(asset_path('project-manager-manual-ticket-creation', '01-ticket-create-form.png')))} }});
        await page.evaluate(() => window.scrollTo(0, 900));
        await page.waitForTimeout(250);
        await page.screenshot({{ path: {js(str(asset_path('project-manager-manual-ticket-creation', '02-ticket-create-routing.png')))} }});
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.fill('input[name="title"]', {js(manual_title)});
        await page.fill('textarea[name="description"]', 'Created during the user-flow training pack capture to document the manual PM routing workflow.');
        await page.locator('select[name="ticket_category"]').selectOption({{ label: 'Support' }});
        await page.locator('select[name="ticket_type_definition"]').selectOption({{ label: 'Query' }});
        await page.locator('select[name="user_type"]').selectOption({{ label: 'Internal' }});
        await page.locator('select[name="source_system"]').selectOption({{ label: 'Project management' }});
        await page.locator('select[name="priority"]').selectOption({{ label: 'Medium' }});
        await page.locator('select[name="department"]').selectOption({{ label: 'Campaign Analytics - Auto route to Analytics Lead' }});
        await page.locator('select[name="campaign"]').selectOption({{ label: 'CardioPlus Unified Care' }});
        await page.fill('input[name="requester_name"]', 'Training Pack Operator');
        await page.fill('input[name="requester_email"]', 'training.pack@example.com');
        await page.fill('input[name="requester_number"]', '9999999999');
        await page.fill('input[name="requester_company"]', 'Inditech');
        await Promise.all([
            page.waitForURL(/\\/ticketing\\/\\d+\\//),
            page.locator('button:has-text("Create ticket")').click(),
        ]);
        await page.waitForTimeout(350);
        await page.screenshot({{ path: {js(str(asset_path('project-manager-manual-ticket-creation', '03-manual-ticket-detail.png')))} }});
        await page.goto({js(BASE_URL + '/ticketing/')}, {{ waitUntil: 'networkidle' }});
        await page.fill('input[placeholder*="Search ticket number"]', {js(manual_title)});
        await Promise.all([
            page.waitForNavigation({{ waitUntil: 'networkidle' }}),
            page.locator('button:has-text("Apply filters")').click(),
        ]);
        await page.waitForTimeout(250);
        await page.screenshot({{ path: {js(str(asset_path('project-manager-manual-ticket-creation', '04-ticket-queue-filtered.png')))} }});
        """
    )

    basic_capture(
        pm,
        BASE_URL + "/app/performance/",
        asset_path("project-manager-campaign-performance-and-reporting", "01-performance-dashboard-overview.png"),
    )
    basic_capture(
        pm,
        BASE_URL + "/app/performance/",
        asset_path("project-manager-campaign-performance-and-reporting", "02-performance-dashboard-kpis.png"),
        scroll_y=420,
    )
    basic_capture(
        pm,
        BASE_URL + "/app/performance/",
        asset_path("project-manager-campaign-performance-and-reporting", "04-performance-dashboard-system-status.png"),
        scroll_y=1100,
    )
    basic_capture(
        pm,
        BASE_URL + "/reporting/contracts/",
        asset_path("project-manager-campaign-performance-and-reporting", "03-reporting-contracts.png"),
    )


def capture_owner_flows(owner: PlaywrightSession) -> None:
    basic_capture(owner, BASE_URL + "/ticketing/", asset_path("department-owner-ticket-execution", "01-owner-ticket-queue.png"))
    basic_capture(owner, BASE_URL + "/ticketing/1/", asset_path("department-owner-ticket-execution", "02-owner-ticket-detail.png"))
    basic_capture(
        owner,
        BASE_URL + "/ticketing/1/",
        asset_path("department-owner-ticket-execution", "03-owner-routing-actions.png"),
        selector='text="Status update"',
    )
    basic_capture(
        owner,
        BASE_URL + "/ticketing/1/",
        asset_path("department-owner-ticket-execution", "04-owner-notes-and-history.png"),
        scroll_y=720,
    )


def capture_widget_assets(public: PlaywrightSession) -> None:
    basic_capture(
        public,
        BASE_URL + "/support/api/doctor/faq-links/",
        asset_path("support-widget-integration", "01-faq-links-api.png"),
        viewport=(1600, 1000),
    )
    doctor_widget = asset_path("doctor-self-service-support", "04-doctor-widget.png")
    copy_asset(doctor_widget, "support-widget-integration", "02-page-wise-widget.png")
    basic_capture(
        public,
        BASE_URL + "/support/doctor/faq/in-clinic-access-verification/doctor-number-verification-screen/widget/?embed=1",
        asset_path("support-widget-integration", "03-combination-widget.png"),
        viewport=(1400, 1080),
    )
    pending_review = asset_path("project-manager-review-other-submissions", "03-pm-pending-review.png")
    copy_asset(pending_review, "support-widget-integration", "04-widget-escalation-context.png")


def main() -> None:
    if not PWCLI.exists():
        raise SystemExit(f"Playwright CLI not found at {PWCLI}")

    ensure_assets()

    run_tag = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    session_tag = datetime.now().strftime("%H%M%S%f")[-8:]
    public = PlaywrightSession(f"tp-pub-{session_tag}")
    pm = PlaywrightSession(f"tp-pm-{session_tag}")
    owner = PlaywrightSession(f"tp-own-{session_tag}")

    for session in (public, pm, owner):
        session.open()

    try:
        issue_text, request_id = capture_public_flows(public, run_tag)
        login_pm(pm)
        capture_pm_flows(pm, run_tag, issue_text, request_id)
        login_owner(owner, "ops@inditech.co.in", "DocsDemo!2026")
        capture_owner_flows(owner)
        capture_widget_assets(public)
    finally:
        for session in (public, pm, owner):
            session.close()


if __name__ == "__main__":
    main()
