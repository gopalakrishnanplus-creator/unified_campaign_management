from unittest.mock import Mock, patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.campaigns.models import Campaign
from apps.reporting.services import build_live_performance_sections
from apps.support_center.services import get_faq_combination
from apps.support_center.models import SupportCategory, SupportItem, SupportSuperCategory
from apps.ticketing.models import Ticket, TicketCategory, TicketNote, TicketTypeDefinition


@override_settings(REPORTING_API_USE_LIVE=False)
class SeededIntegrationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo_data")
        cls.pm_user = User.objects.get(email=settings.PROJECT_MANAGER_EMAIL)
        cls.campaign = Campaign.objects.get(slug="cardioplus-unified-care")
        cls.ticket = Ticket.objects.get(title="In-clinic collateral is not opening")

    def test_public_pages_render(self):
        paths = [
            reverse("home"),
            reverse("support_center:landing", kwargs={"user_type": "doctor"}),
            reverse("support_center:landing", kwargs={"user_type": "clinic_staff"}),
            reverse("support_center:landing", kwargs={"user_type": "brand_manager"}),
            reverse("support_center:landing", kwargs={"user_type": "field_rep"}),
            reverse("support_center:landing", kwargs={"user_type": "patient"}),
            "/accounts/login/?next=/app/",
        ]
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_dev_login_redirects_to_dashboard(self):
        response = self.client.get(reverse("accounts:dev_login"))
        self.assertRedirects(response, reverse("dashboards:home"))

    @patch("apps.dashboards.services.requests.get")
    def test_authenticated_pages_render(self, mock_get):
        mock_get.return_value = Mock(status_code=200)
        self.client.force_login(self.pm_user)
        urls = [
            reverse("dashboards:home"),
            reverse("dashboards:performance"),
            reverse("ticketing:list"),
            reverse("ticketing:distribution"),
            reverse("ticketing:create"),
            reverse("campaigns:list"),
            reverse("campaigns:detail", kwargs={"slug": self.campaign.slug}),
            reverse("ticketing:detail", kwargs={"pk": self.ticket.pk}),
            reverse("reporting:contracts"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_ticket_creation_supports_dynamic_ticket_types(self):
        self.client.force_login(self.pm_user)
        category = TicketCategory.objects.order_by("display_order", "name").first()
        response = self.client.post(
            reverse("ticketing:create"),
            data={
                "title": "Daily dashboard sync failed",
                "description": "A new manually reported issue for validation.",
                "ticket_category": category.pk,
                "ticket_type_definition": "",
                "new_ticket_type_name": "Dashboard sync anomaly",
                "user_type": Ticket.UserType.INTERNAL,
                "source_system": Ticket.SourceSystem.PROJECT_MANAGER,
                "priority": Ticket.Priority.CRITICAL,
                "department": self.ticket.department.pk,
                "campaign": self.campaign.pk,
                "requester_name": "Campaign PM",
                "requester_email": "campaignpm+dynamic@example.com",
                "requester_company": "Inditech",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        created_ticket = Ticket.objects.get(requester_email="campaignpm+dynamic@example.com")
        self.assertEqual(created_ticket.ticket_category, category)
        self.assertEqual(created_ticket.ticket_type, "Dashboard sync anomaly")
        self.assertEqual(created_ticket.ticket_type_definition.name, "Dashboard sync anomaly")
        self.assertEqual(created_ticket.priority, Ticket.Priority.CRITICAL)

    def test_default_ticket_taxonomy_is_seeded(self):
        expected = {
            "Bug": {"Functional", "UI", "Performance", "Error"},
            "Feature Request": {"New Feature", "Enhancement"},
            "Data Issue": {"Missing", "Incorrect", "Delay"},
            "Access": {"Login", "Permission"},
            "Integration": {"Failure", "Sync"},
            "Billing": {"Invoice", "Payment", "Subscription"},
            "Support": {"How-to", "Query"},
            "Content": {"Incorrect", "Update"},
            "Incident": {"System Down", "High Impact"},
        }
        for category_name, type_names in expected.items():
            with self.subTest(category=category_name):
                category = TicketCategory.objects.get(name=category_name)
                actual_types = set(
                    TicketTypeDefinition.objects.filter(category=category).values_list("name", flat=True)
                )
                self.assertTrue(type_names.issubset(actual_types))

    def test_seeded_tickets_follow_standardized_taxonomy(self):
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.ticket_category.name, "Content")
        self.assertEqual(self.ticket.ticket_type, "Update")

    @patch("apps.dashboards.services.requests.get")
    def test_project_manager_dashboard_shows_status_codes(self, mock_get):
        def response_for(url, timeout=None, allow_redirects=False):
            response = Mock()
            if "red_flag_alert" in url:
                response.status_code = 503
            elif "patient_education" in url:
                response.status_code = 404
            else:
                response.status_code = 200
            return response

        mock_get.side_effect = response_for
        self.client.force_login(self.pm_user)
        response = self.client.get(reverse("dashboards:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System-wise and URL-wise status availability")
        self.assertContains(response, "503")
        self.assertContains(response, "404")
        self.assertContains(response, "Campaign performance")

    def test_reporting_api_endpoints_return_data(self):
        self.client.force_login(self.pm_user)
        endpoints = [
            reverse("reporting:contracts_api"),
            reverse("reporting:subsystem_feed", kwargs={"subsystem": "red_flag_alert"}),
            reverse("reporting:subsystem_feed", kwargs={"subsystem": "in_clinic"}),
            reverse("reporting:subsystem_feed", kwargs={"subsystem": "patient_education"}),
            reverse("reporting:subsystem_feed", kwargs={"subsystem": "adoption"}),
            reverse("reporting:subsystem_feed", kwargs={"subsystem": "external_growth"}),
        ]
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint)
                self.assertEqual(response.status_code, 200)

    def test_support_item_escalation_creates_ticket(self):
        item = SupportItem.objects.get(slug="weekly-report-missing")
        ticket_count = Ticket.objects.count()
        response = self.client.post(
            reverse(
                "support_center:item_detail",
                kwargs={
                    "user_type": "brand_manager",
                    "super_slug": item.category.super_category.slug,
                    "category_slug": item.category.slug,
                    "item_slug": item.slug,
                },
            ),
            data={
                "requester_name": "Priya Shah",
                "requester_email": "priya.new@example.com",
                "requester_company": "CardioPlus",
                "campaign": self.campaign.pk,
                "subject": item.name,
                "free_text": "Need the analytics report regenerated.",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Ticket.objects.count(), ticket_count + 1)

    def test_ticket_workflow_actions(self):
        operations_user = self.ticket.direct_recipient
        backup_user = User.objects.create_user(
            email="backup.ops@example.com",
            full_name="Backup Operations",
            role=User.Role.SUPPORT_AGENT,
            department=self.ticket.department,
            is_staff=True,
        )
        self.client.force_login(operations_user)
        detail_url = reverse("ticketing:detail", kwargs={"pk": self.ticket.pk})

        note_response = self.client.post(
            detail_url,
            data={
                "action": "note",
                "body": "Added a diagnostic note from test coverage.",
                "attachments": SimpleUploadedFile("note.txt", b"attachment"),
            },
            follow=True,
        )
        self.assertEqual(note_response.status_code, 200)
        self.assertTrue(TicketNote.objects.filter(ticket=self.ticket, body__icontains="diagnostic note").exists())

        status_response = self.client.post(
            detail_url,
            data={"action": "status", "status": Ticket.Status.IN_PROCESS},
            follow=True,
        )
        self.assertEqual(status_response.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.IN_PROCESS)

        delegate_response = self.client.post(
            detail_url,
            data={"action": "delegate", "assignee": backup_user.pk},
            follow=True,
        )
        self.assertEqual(delegate_response.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.current_assignee, backup_user)

    def test_support_assistant_escalates_ticket_case(self):
        assistant_super = SupportSuperCategory.objects.create(name="Assistant Flow Tests", slug="assistant-flow-tests")
        assistant_category = SupportCategory.objects.create(
            super_category=assistant_super,
            name="Verification Screen",
            slug="verification-screen",
        )
        SupportItem.objects.create(
            category=assistant_category,
            name="FAQ step for assistant",
            slug="faq-step-for-assistant",
            summary="Try the standard fix first.",
            knowledge_type=SupportItem.KnowledgeType.FAQ,
            response_mode=SupportItem.ResponseMode.STANDARDIZED,
            solution_title="FAQ step",
            solution_body="Ask the user to retry with the latest link.",
            ticket_department=self.ticket.department,
            default_ticket_type="Assistant issue",
            source_system="In-clinic",
            source_flow="Assistant Flow",
            is_visible_to_doctors=True,
            is_visible_to_clinic_staff=False,
            is_visible_to_brand_managers=False,
            is_visible_to_field_reps=False,
        )
        ticket_case = SupportItem.objects.create(
            category=assistant_category,
            name="Ticket case for assistant",
            slug="ticket-case-for-assistant",
            summary="Escalate after FAQ failure.",
            knowledge_type=SupportItem.KnowledgeType.TICKET_CASE,
            response_mode=SupportItem.ResponseMode.DIRECT_TICKET,
            solution_body="Escalate this to the technical support queue.",
            ticket_department=self.ticket.department,
            default_ticket_type="Assistant issue",
            source_system="In-clinic",
            source_flow="Assistant Flow",
            ticket_required=True,
            is_visible_to_doctors=True,
            is_visible_to_clinic_staff=False,
            is_visible_to_brand_managers=False,
            is_visible_to_field_reps=False,
        )

        assistant_url = reverse("support_center:assistant", kwargs={"user_type": "doctor"})
        ticket_count = Ticket.objects.count()

        self.assertEqual(self.client.get(assistant_url).status_code, 200)
        self.client.post(assistant_url, data={"action": "choose_system", "system": "In-clinic"})
        self.client.post(assistant_url, data={"action": "choose_flow", "flow": "Assistant Flow"})
        self.client.post(assistant_url, data={"action": "choose_category", "category_id": assistant_category.pk})
        self.client.post(assistant_url, data={"action": "faq_feedback", "resolution": "unresolved"})
        self.client.post(assistant_url, data={"action": "select_ticket_case", "item_id": ticket_case.pk})
        response = self.client.post(
            assistant_url,
            data={
                "action": "create_ticket",
                "requester_name": "Support Assistant User",
                "requester_email": "assistant.user@example.com",
                "requester_company": "Inditech Clinic",
                "campaign": self.campaign.pk,
                "subject": ticket_case.name,
                "free_text": "The FAQ did not solve the issue.",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Ticket.objects.count(), ticket_count + 1)
        created_ticket = Ticket.objects.get(requester_email="assistant.user@example.com")
        self.assertEqual(created_ticket.title, ticket_case.name)
        self.assertEqual(created_ticket.source_system, Ticket.SourceSystem.IN_CLINIC)

    def test_faq_page_api_and_widget_render(self):
        faq_page_url = reverse(
            "support_center:faq_super_category",
            kwargs={"user_type": "brand_manager", "super_slug": "access-login"},
        )
        faq_api_url = reverse(
            "support_center:faq_combination_api",
            kwargs={"user_type": "brand_manager", "super_slug": "access-login", "category_slug": "authentication"},
        )
        faq_links_url = reverse("support_center:faq_links_api", kwargs={"user_type": "brand_manager"})
        widget_url = reverse(
            "support_center:faq_widget",
            kwargs={"user_type": "brand_manager", "super_slug": "access-login", "category_slug": "authentication"},
        )

        page_response = self.client.get(faq_page_url)
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, "Authentication")

        links_response = self.client.get(faq_links_url)
        self.assertEqual(links_response.status_code, 200)
        self.assertEqual(links_response.headers["Access-Control-Allow-Origin"], "*")
        self.assertGreaterEqual(links_response.json()["count"], 1)

        api_response = self.client.get(faq_api_url)
        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(api_response.headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(api_response.json()["faq_count"], 1)
        self.assertIn("embed_url", api_response.json())

        widget_response = self.client.get(f"{widget_url}?embed=1")
        self.assertEqual(widget_response.status_code, 200)
        self.assertNotIn("X-Frame-Options", widget_response.headers)
        self.assertContains(widget_response, "Customer chat support")


@override_settings(REPORTING_API_USE_LIVE=True)
class LiveReportingServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo_data")

    @patch("apps.reporting.services.requests.get")
    def test_reporting_feed_uses_live_payload_when_available(self, mock_get):
        payloads = {
            settings.REPORTING_API_RED_FLAG_ALERT_URL: {
                "subsystem": "red_flag_alert",
                "count": 1,
                "results": [
                    {
                        "campaign": "growth-clinic",
                        "clinic_group": "Delhi",
                        "clinic": "Clinic A",
                        "form_fills": 3,
                        "red_flags_total": 5,
                        "patient_video_views": 1,
                        "reports_emailed_to_doctors": 2,
                        "form_shares": 1,
                        "patient_scans": 1,
                        "follow_ups_scheduled": 0,
                        "reminders_sent": 0,
                    }
                ],
            }
        }

        def response_for(url, timeout):
            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = payloads[url]
            return response

        mock_get.side_effect = response_for
        response = self.client.get(reverse("reporting:subsystem_feed", kwargs={"subsystem": "red_flag_alert"}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "live")
        self.assertEqual(response.json()["results"][0]["form_fills"], 3)

    @override_settings(WORDPRESS_CERTIFICATE_COURSE_IDS="8693")
    @patch("apps.reporting.services.requests.get")
    def test_live_performance_sections_derive_adoption_and_external_growth(self, mock_get):
        red_flag_payload = {
            "subsystem": "red_flag_alert",
            "count": 2,
            "results": [
                {
                    "campaign": "growth-clinic",
                    "clinic_group": "Delhi",
                    "clinic": "Clinic A",
                    "form_fills": 3,
                    "red_flags_total": 5,
                    "patient_video_views": 1,
                    "reports_emailed_to_doctors": 2,
                    "form_shares": 1,
                    "patient_scans": 1,
                    "follow_ups_scheduled": 0,
                    "reminders_sent": 0,
                },
                {
                    "campaign": "growth-clinic",
                    "clinic_group": "Mumbai",
                    "clinic": "Clinic B",
                    "form_fills": 2,
                    "red_flags_total": 4,
                    "patient_video_views": 0,
                    "reports_emailed_to_doctors": 1,
                    "form_shares": 0,
                    "patient_scans": 0,
                    "follow_ups_scheduled": 1,
                    "reminders_sent": 0,
                },
            ],
        }
        in_clinic_payload = {
            "subsystem": "in_clinic",
            "count": 2,
            "results": [
                {
                    "campaign": "campaign-a",
                    "clinic_group": "Delhi",
                    "clinic": "clinic-a",
                    "doctor": "doctor-a",
                    "field_rep": "",
                    "shares": 2,
                    "link_opens": 1,
                    "pdf_reads_completed": 1,
                    "video_views": 0,
                    "video_completions": 0,
                    "pdf_downloads": 1,
                },
                {
                    "campaign": "campaign-b",
                    "clinic_group": "Mumbai",
                    "clinic": "clinic-b",
                    "doctor": "doctor-b",
                    "field_rep": "",
                    "shares": 0,
                    "link_opens": 0,
                    "pdf_reads_completed": 0,
                    "video_views": 0,
                    "video_completions": 0,
                    "pdf_downloads": 0,
                },
            ],
        }
        patient_education_payload = {
            "subsystem": "patient_education",
            "count": 2,
            "results": [
                {
                    "campaign": "campaign-a",
                    "clinic_group": "Delhi",
                    "clinic": "Clinic A",
                    "video_views": 3,
                    "video_completions": 1,
                    "cluster_shares": 1,
                    "patient_scans": 1,
                    "banner_clicks": 0,
                },
                {
                    "campaign": "campaign-b",
                    "clinic_group": "Mumbai",
                    "clinic": "Clinic C",
                    "video_views": 1,
                    "video_completions": 0,
                    "cluster_shares": 0,
                    "patient_scans": 0,
                    "banner_clicks": 0,
                },
            ],
        }

        def response_for(url, timeout=None, params=None):
            response = Mock()
            response.raise_for_status.return_value = None
            if url == settings.REPORTING_API_RED_FLAG_ALERT_URL:
                response.json.return_value = red_flag_payload
            elif url == settings.REPORTING_API_IN_CLINIC_URL:
                response.json.return_value = in_clinic_payload
            elif url == settings.REPORTING_API_PATIENT_EDUCATION_URL:
                response.json.return_value = patient_education_payload
            elif url == settings.WORDPRESS_HELPER_URL and params and params.get("ld_api") == "webinar_registrations":
                response.json.return_value = {
                    "data": [
                        {"event_title": "SAPA Growth Clinics - Introduction & Q&A", "email": "doctor1@example.com"},
                        {"event_title": "SAPA Growth Clinics - Introduction & Q&A", "email": "doctor2@example.com"},
                    ]
                }
            elif url == settings.WORDPRESS_HELPER_URL and params and params.get("ld_api") == "course_breakdown":
                response.json.return_value = {
                    "data": [
                        {"progress_status": "Completed", "user_email": "doctor1@example.com", "display_name": "Clinic A", "phone": ""},
                        {"progress_status": "Completed", "user_email": "doctor2@example.com", "display_name": "External Doctor", "phone": ""},
                    ]
                }
            else:
                raise AssertionError(f"Unexpected request: {url} params={params}")
            return response

        mock_get.side_effect = response_for
        sections = build_live_performance_sections()

        self.assertEqual(sections["adoption_rows"][0]["clinics_added_total"], 2)
        self.assertEqual(sections["adoption_rows"][0]["clinics_with_shares_total"], 1)
        self.assertEqual(sections["adoption_rows"][2]["doctors_added_total"], 2)
        self.assertEqual(sections["external_growth_totals"]["webinar_attendees"], 2)
        self.assertEqual(sections["external_growth_totals"]["certificate_completed"], 2)
        self.assertEqual(sections["external_growth_totals"]["onboarded_certificate_completed"], 1)
        self.assertEqual(sections["external_growth_totals"]["non_onboarded_certificate_completed"], 1)


class SupportBaselineCommandTests(TestCase):
    def test_seed_support_baseline_restores_static_widget_catalog_entries(self):
        call_command("seed_support_baseline")

        self.assertTrue(get_faq_combination("doctor", "reporting-analytics", "reports-insights"))
        self.assertTrue(get_faq_combination("clinic_staff", "campaign-operations", "sharing-activation"))
        self.assertTrue(get_faq_combination("brand_manager", "access-login", "authentication"))
        self.assertTrue(get_faq_combination("field_rep", "access-login", "authentication"))
