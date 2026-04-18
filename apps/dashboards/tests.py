from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.campaigns.models import Campaign
from apps.reporting.services import build_live_performance_sections
from apps.support_center.services import get_faq_combination
from apps.support_center.models import SupportCategory, SupportItem, SupportPage, SupportRequest, SupportSuperCategory
from apps.ticketing.models import Department, Ticket, TicketAttachment, TicketCategory, TicketNote, TicketTypeDefinition
from apps.ticketing.external_ticketing import sync_external_directory
from apps.ticketing.services import create_ticket


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
            reverse("support_center:landing", kwargs={"user_type": "publisher"}),
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

    @patch("apps.dashboards.services.requests.get")
    def test_pm_pages_and_ticket_create_hide_campaign_filters(self, mock_get):
        mock_get.return_value = Mock(status_code=200)
        self.client.force_login(self.pm_user)

        dashboard_response = self.client.get(reverse("dashboards:home"))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertNotContains(dashboard_response, 'name="campaign"', html=False)

        performance_response = self.client.get(reverse("dashboards:performance"))
        self.assertEqual(performance_response.status_code, 200)
        self.assertNotContains(performance_response, 'name="campaign"', html=False)

        ticket_create_response = self.client.get(reverse("ticketing:create"))
        self.assertEqual(ticket_create_response.status_code, 200)
        self.assertNotContains(ticket_create_response, 'id="id_campaign"', html=False)

    @override_settings(EXTERNAL_TICKETING_SYNC_ENABLED=False)
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
                "status": Ticket.Status.NOT_STARTED,
                "department": self.ticket.department.pk,
                "campaign": self.campaign.pk,
                "requester_name": "Campaign PM",
                "requester_email": "campaignpm+dynamic@example.com",
                "requester_number": "+919999999999",
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

    @patch("apps.dashboards.services.requests.get")
    def test_pm_dashboard_uses_decluttered_queue_layout(self, mock_get):
        mock_get.return_value = Mock(status_code=200)
        self.client.force_login(self.pm_user)

        response = self.client.get(reverse("dashboards:home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertContains(response, "View Visualizations")
        self.assertNotContains(response, "Monitor ticket load, spot bottlenecks, and jump straight into the queues that need attention.")
        self.assertNotContains(response, "Every row links to the full ticket detail page. Use the full queue for filtering and sorting.")
        self.assertNotContains(response, "Operational Details")
        self.assertNotContains(response, "Volume, resolution quality, and bottlenecks")
        self.assertNotContains(response, "Screening, adoption, and content metrics are separated to keep this dashboard focused on decisions and operations.")
        self.assertLess(content.index('metric-label">Open tickets'), content.index('metric-label">Critical'))
        self.assertLess(content.index('metric-label">Critical'), content.index('metric-label">In progress'))
        self.assertLess(content.index('metric-label">In progress'), content.index('metric-label">Closed'))
        self.assertLess(content.index('metric-label">Closed'), content.index('metric-label">Total tickets'))
        self.assertLess(content.index("Other Issues"), content.index("Critical Tickets"))
        self.assertLess(content.index("Critical Tickets"), content.index("Full Ticket Queue"))

    @patch("apps.dashboards.services.requests.get")
    @override_settings(
        EXTERNAL_TICKETING_SYNC_ENABLED=False,
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        SENDGRID_API_KEY="",
    )
    def test_project_manager_can_escalate_ticket_from_dashboard_queue(self, mock_get):
        mock_get.return_value = Mock(status_code=200)
        standard_ticket = Ticket.objects.create(
            title="Standard high priority issue",
            description="Needs attention but is not escalated yet.",
            ticket_type="Functional",
            user_type=Ticket.UserType.INTERNAL,
            source_system=Ticket.SourceSystem.PROJECT_MANAGER,
            priority=Ticket.Priority.HIGH,
            status=Ticket.Status.NOT_STARTED,
            department=self.ticket.department,
            campaign=self.campaign,
            created_by=self.pm_user,
            submitted_by=self.pm_user,
            direct_recipient=self.ticket.department.default_recipient,
            current_assignee=self.ticket.department.default_recipient,
            requester_name="Standard Queue User",
            requester_email="standard-queue@example.com",
            requester_number="+919900000001",
            requester_company="Inditech",
        )
        escalated_ticket = Ticket.objects.create(
            title="Needs PM escalation",
            description="This should move to the top after escalation.",
            ticket_type="Functional",
            user_type=Ticket.UserType.INTERNAL,
            source_system=Ticket.SourceSystem.PROJECT_MANAGER,
            priority=Ticket.Priority.CRITICAL,
            status=Ticket.Status.NOT_STARTED,
            department=self.ticket.department,
            campaign=self.campaign,
            created_by=self.pm_user,
            submitted_by=self.pm_user,
            direct_recipient=self.ticket.department.default_recipient,
            current_assignee=self.ticket.department.default_recipient,
            requester_name="Escalation Queue User",
            requester_email="escalation-queue@example.com",
            requester_number="+919900000002",
            requester_company="Inditech",
        )

        self.client.force_login(self.pm_user)
        response = self.client.post(
            reverse("ticketing:escalate", kwargs={"pk": escalated_ticket.pk}),
            data={"next": f"{reverse('dashboards:home')}#critical-ticket-review"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        escalated_ticket.refresh_from_db()
        self.assertTrue(escalated_ticket.is_escalated)
        self.assertEqual(escalated_ticket.priority, Ticket.Priority.CRITICAL)
        self.assertContains(response, f"{escalated_ticket.ticket_number} marked as High Priority and moved to the top of the queue.")
        self.assertContains(response, "High Priority / Escalated")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].to,
            [self.ticket.department.support_email, self.ticket.department.default_recipient.email],
        )
        self.assertIn(escalated_ticket.ticket_number, mail.outbox[0].subject)
        self.assertIn("already critical ticket", mail.outbox[0].alternatives[0][0])
        self.assertIn(self.ticket.department.name, mail.outbox[0].body)
        content = response.content.decode()
        self.assertLess(content.index(escalated_ticket.ticket_number), content.index(standard_ticket.ticket_number))

    @patch("apps.dashboards.services.requests.get")
    @override_settings(
        EXTERNAL_TICKETING_SYNC_ENABLED=False,
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        SENDGRID_API_KEY="",
    )
    def test_project_manager_cannot_escalate_non_critical_ticket(self, mock_get):
        mock_get.return_value = Mock(status_code=200)
        ticket = Ticket.objects.create(
            title="High priority issue",
            description="This should stay high until PM marks it critical first.",
            ticket_type="Functional",
            user_type=Ticket.UserType.INTERNAL,
            source_system=Ticket.SourceSystem.PROJECT_MANAGER,
            priority=Ticket.Priority.HIGH,
            status=Ticket.Status.NOT_STARTED,
            department=self.ticket.department,
            campaign=self.campaign,
            created_by=self.pm_user,
            submitted_by=self.pm_user,
            direct_recipient=self.ticket.department.default_recipient,
            current_assignee=self.ticket.department.default_recipient,
            requester_name="High Priority User",
            requester_email="high-priority@example.com",
            requester_number="+919900000010",
            requester_company="Inditech",
        )

        self.client.force_login(self.pm_user)
        response = self.client.post(
            reverse("ticketing:escalate", kwargs={"pk": ticket.pk}),
            data={"next": f"{reverse('dashboards:home')}#critical-ticket-review"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertFalse(ticket.is_escalated)
        self.assertEqual(ticket.priority, Ticket.Priority.HIGH)
        self.assertContains(response, f"{ticket.ticket_number} can only be escalated after it is marked Critical.")
        self.assertEqual(len(mail.outbox), 0)

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

    @override_settings(EXTERNAL_TICKETING_SYNC_ENABLED=False)
    def test_ticket_views_render_timestamps_in_india_time(self):
        utc_zone = ZoneInfo("UTC")
        note = TicketNote.objects.create(ticket=self.ticket, author=self.pm_user, body="Timezone rendering check.")
        routing_event = self.ticket.routing_events.order_by("created_at").first()

        Ticket.objects.filter(pk=self.ticket.pk).update(
            created_at=datetime(2026, 1, 1, 6, 0, tzinfo=utc_zone),
            external_ticket_number="CLT-IST-CHECK",
            external_ticket_synced_at=datetime(2026, 1, 1, 9, 15, tzinfo=utc_zone),
        )
        TicketNote.objects.filter(pk=note.pk).update(created_at=datetime(2026, 1, 1, 7, 0, tzinfo=utc_zone))
        self.ticket.routing_events.filter(pk=routing_event.pk).update(created_at=datetime(2026, 1, 1, 8, 0, tzinfo=utc_zone))

        self.client.force_login(self.pm_user)
        list_response = self.client.get(reverse("ticketing:list"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "01 Jan 2026 11:30")
        self.assertNotContains(list_response, "01 Jan 2026 06:00")

        detail_response = self.client.get(reverse("ticketing:detail", kwargs={"pk": self.ticket.pk}))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "01 Jan 2026 12:30")
        self.assertContains(detail_response, "01 Jan 2026 13:30")
        self.assertContains(detail_response, "01 Jan 2026 14:45")

    def test_support_assistant_records_other_issue_for_pm_review(self):
        assistant_super = SupportSuperCategory.objects.create(name="Assistant Flow Tests", slug="assistant-flow-tests")
        assistant_category = SupportCategory.objects.create(
            super_category=assistant_super,
            name="Verification Screen",
            slug="verification-screen",
        )
        assistant_page = SupportPage.objects.create(
            name="Verification Page",
            slug="verification-page",
            source_system="In-clinic",
            source_flow="Assistant Flow",
        )
        SupportItem.objects.create(
            page=assistant_page,
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

        assistant_url = reverse("support_center:assistant", kwargs={"user_type": "doctor"})
        self.assertEqual(self.client.get(assistant_url).status_code, 200)
        self.client.post(assistant_url, data={"action": "choose_system", "system": "In-clinic"})
        self.client.post(assistant_url, data={"action": "choose_flow", "flow": "Assistant Flow"})
        self.client.post(assistant_url, data={"action": "choose_category", "category_id": assistant_category.pk})
        selection_response = self.client.get(assistant_url)
        self.assertContains(selection_response, "Other")
        self.client.post(assistant_url, data={"action": "select_faq", "selection": "other"})
        response = self.client.post(
            assistant_url,
            data={
                "action": "submit_other_issue",
                "requester_name": "Doctor Widget User",
                "requester_number": "+916666666666",
                "requester_email": "doctor.widget@example.com",
                "free_text": "The FAQ list did not cover the patient verification issue.",
                "uploaded_file": SimpleUploadedFile("evidence.webp", b"image-bytes", content_type="image/webp"),
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        support_request = SupportRequest.objects.get(status=SupportRequest.Status.PENDING_PM_REVIEW)
        self.assertEqual(support_request.support_category, assistant_category)
        self.assertEqual(support_request.support_page, assistant_page)
        self.assertEqual(support_request.support_super_category, assistant_super)
        self.assertEqual(support_request.source_system, "In-clinic")
        self.assertEqual(support_request.source_flow, "Assistant Flow")
        self.assertTrue(support_request.uploaded_file.name.endswith(".webp"))
        self.assertTrue(support_request.queue_ticket_number.startswith("PMQ-"))
        self.assertFalse(Ticket.objects.filter(support_request=support_request).exists())
        self.assertContains(response, support_request.queue_ticket_number)
        self.assertContains(response, settings.PM_QUEUE_ESTIMATED_RESPONSE_TIME)

    def test_support_landing_shows_page_and_section_faqs_without_free_text_form(self):
        response = self.client.get(reverse("support_center:landing", kwargs={"user_type": "brand_manager"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "sections")
        self.assertNotContains(response, "Free-text support request")
        self.assertContains(response, "Standalone widget")

    def test_faq_page_api_and_widget_render(self):
        page = SupportPage.objects.get(slug="customer-support-authentication-page")
        faq_page_url = reverse(
            "support_center:faq_page",
            kwargs={"user_type": "brand_manager", "page_slug": page.slug},
        )
        faq_api_url = reverse(
            "support_center:faq_page_api",
            kwargs={"user_type": "brand_manager", "page_slug": page.slug},
        )
        faq_links_url = reverse("support_center:faq_links_api", kwargs={"user_type": "brand_manager"})
        widget_url = reverse(
            "support_center:faq_page_widget",
            kwargs={"user_type": "brand_manager", "page_slug": page.slug},
        )

        page_response = self.client.get(faq_page_url)
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, page.name)

        links_response = self.client.get(faq_links_url)
        self.assertEqual(links_response.status_code, 200)
        self.assertEqual(links_response.headers["Access-Control-Allow-Origin"], "*")
        self.assertGreaterEqual(links_response.json()["count"], 1)
        self.assertIn("source_system", links_response.json()["results"][0])
        self.assertIn("page", links_response.json()["results"][0])
        self.assertIn("embed=1", links_response.json()["results"][0]["embed_url"])

        api_response = self.client.get(faq_api_url)
        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(api_response.headers["Access-Control-Allow-Origin"], "*")
        self.assertGreaterEqual(api_response.json()["faq_count"], 1)
        self.assertGreaterEqual(api_response.json()["section_count"], 1)
        self.assertIn("embed_url", api_response.json())
        self.assertIn("sections", api_response.json())

        widget_response = self.client.get(f"{widget_url}?embed=1")
        self.assertEqual(widget_response.status_code, 200)
        self.assertNotIn("X-Frame-Options", widget_response.headers)
        self.assertContains(widget_response, "Support Bot")
        self.assertContains(widget_response, 'id="restart-page-button"', html=False)
        self.assertContains(widget_response, 'id="restart-section-button"', html=False)
        self.assertContains(widget_response, "Sections")
        self.assertContains(widget_response, "Other")
        self.assertNotContains(widget_response, "Open full FAQ page")

    def test_widget_other_issue_submission_records_pm_review_item(self):
        faq_super = SupportSuperCategory.objects.create(name="Widget Flow Tests", slug="widget-flow-tests")
        faq_category = SupportCategory.objects.create(super_category=faq_super, name="Landing Screen", slug="landing-screen")
        faq_page = SupportPage.objects.create(name="Patient Landing Page", slug="patient-landing-page", source_system="Patient Education", source_flow="Widget Flow")
        SupportItem.objects.create(
            page=faq_page,
            category=faq_category,
            name="Widget FAQ",
            slug="widget-faq",
            summary="Basic help text.",
            knowledge_type=SupportItem.KnowledgeType.FAQ,
            solution_body="Use the standard widget answer.",
            source_system="Patient Education",
            source_flow="Widget Flow",
            is_visible_to_patients=True,
            is_visible_to_doctors=False,
            is_visible_to_clinic_staff=False,
            is_visible_to_brand_managers=False,
            is_visible_to_field_reps=False,
        )
        response = self.client.post(
            reverse(
                "support_center:faq_page_other_issue",
                kwargs={"user_type": "patient", "page_slug": faq_page.slug},
            ),
            data={
                "requester_name": "Patient Widget User",
                "requester_email": "patient@example.com",
                "requester_number": "+911111111111",
                "free_text": "Need help with a patient screen issue not listed here.",
                "uploaded_file": SimpleUploadedFile("patient.png", b"image-bytes", content_type="image/png"),
                "selected_section_slug": faq_super.slug,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertTrue(payload["ticket_id"].startswith("PMQ-"))
        self.assertEqual(payload["estimated_response_time"], settings.PM_QUEUE_ESTIMATED_RESPONSE_TIME)

        support_request = SupportRequest.objects.get(pk=payload["request_id"])
        self.assertEqual(support_request.status, SupportRequest.Status.PENDING_PM_REVIEW)
        self.assertEqual(support_request.source_system, "Patient Education")
        self.assertEqual(support_request.source_flow, "Widget Flow")
        self.assertEqual(support_request.support_page, faq_page)
        self.assertEqual(support_request.support_super_category, faq_super)
        self.assertIsNone(support_request.support_category)
        self.assertEqual(support_request.requester_number, "+911111111111")
        self.assertTrue(support_request.uploaded_file.name.endswith(".png"))
        self.assertEqual(support_request.queue_ticket_number, payload["ticket_id"])

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", SENDGRID_API_KEY="")
    def test_widget_other_issue_submission_sends_queue_confirmation_email(self):
        faq_super = SupportSuperCategory.objects.create(name="Email Widget Tests", slug="email-widget-tests")
        faq_category = SupportCategory.objects.create(super_category=faq_super, name="Sharing Screen", slug="sharing-screen")
        faq_page = SupportPage.objects.create(name="Doctor Sharing Page", slug="doctor-sharing-page", source_system="In-clinic", source_flow="Email Flow")
        SupportItem.objects.create(
            page=faq_page,
            category=faq_category,
            name="Email widget FAQ",
            slug="email-widget-faq",
            summary="Basic help text.",
            knowledge_type=SupportItem.KnowledgeType.FAQ,
            solution_body="Use the standard widget answer.",
            source_system="In-clinic",
            source_flow="Email Flow",
            is_visible_to_doctors=True,
            is_visible_to_clinic_staff=False,
            is_visible_to_brand_managers=False,
            is_visible_to_field_reps=False,
            is_visible_to_patients=False,
        )

        response = self.client.post(
            reverse(
                "support_center:faq_page_other_issue",
                kwargs={"user_type": "doctor", "page_slug": faq_page.slug},
            ),
            data={
                "requester_name": "Doctor Email User",
                "requester_email": "doctor.email@example.com",
                "requester_number": "+918888888888",
                "device_type": "android",
                "device": "phone",
                "free_text": "I am seeing a blank sharing screen.",
                "uploaded_file": SimpleUploadedFile("share.png", b"image-bytes", content_type="image/png"),
                "selected_section_slug": faq_super.slug,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        support_request = SupportRequest.objects.get(pk=payload["request_id"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["doctor.email@example.com"])
        self.assertIn(support_request.queue_ticket_number, mail.outbox[0].subject)
        self.assertIn(support_request.queue_ticket_number, mail.outbox[0].body)
        self.assertIn(settings.PM_QUEUE_ESTIMATED_RESPONSE_TIME, mail.outbox[0].body)
        self.assertIn("Android", mail.outbox[0].alternatives[0][0])
        self.assertIn("Phone", mail.outbox[0].alternatives[0][0])

    def test_widget_other_issue_uses_selected_faq_context_when_category_has_mixed_systems(self):
        faq_super = SupportSuperCategory.objects.create(name="Mixed Widget Tests", slug="mixed-widget-tests")
        faq_category = SupportCategory.objects.create(super_category=faq_super, name="Shared Screen", slug="shared-screen")
        faq_page = SupportPage.objects.create(name="Shared Page", slug="shared-page", source_system="", source_flow="")
        first_faq = SupportItem.objects.create(
            page=faq_page,
            category=faq_category,
            name="Generic support question",
            slug="generic-support-question",
            knowledge_type=SupportItem.KnowledgeType.FAQ,
            solution_body="Generic support answer.",
            source_system="Customer support",
            source_flow="General support",
            is_visible_to_brand_managers=True,
            is_visible_to_doctors=False,
            is_visible_to_clinic_staff=False,
            is_visible_to_field_reps=False,
        )
        second_faq = SupportItem.objects.create(
            page=faq_page,
            category=faq_category,
            name="In-clinic issue question",
            slug="in-clinic-issue-question",
            knowledge_type=SupportItem.KnowledgeType.FAQ,
            solution_body="In-clinic answer.",
            source_system="In-clinic",
            source_flow="In-clinic Content",
            is_visible_to_brand_managers=True,
            is_visible_to_doctors=False,
            is_visible_to_clinic_staff=False,
            is_visible_to_field_reps=False,
            display_order=2,
        )

        response = self.client.post(
            reverse(
                "support_center:faq_page_other_issue",
                kwargs={"user_type": "brand_manager", "page_slug": faq_page.slug},
            ),
            data={
                "requester_name": "Brand Manager",
                "requester_email": "brand.manager@example.com",
                "requester_number": "+912222222222",
                "free_text": "The in-clinic screen is blank and I need help.",
                "uploaded_file": SimpleUploadedFile("evidence.png", b"image-bytes", content_type="image/png"),
                "selected_faq_id": second_faq.pk,
                "selected_section_slug": faq_super.slug,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])

        support_request = SupportRequest.objects.get(pk=payload["request_id"])
        self.assertEqual(support_request.support_page, faq_page)
        self.assertEqual(support_request.support_super_category, faq_super)
        self.assertEqual(support_request.support_category, faq_category)
        self.assertEqual(support_request.source_system, "In-clinic")
        self.assertEqual(support_request.source_flow, "In-clinic Content")
        self.assertNotEqual(support_request.source_system, first_faq.source_system)

    def test_widget_other_issue_prefers_explicit_system_context_over_faq_source_system(self):
        faq_super = SupportSuperCategory.objects.create(name="Override Widget Tests", slug="override-widget-tests")
        faq_category = SupportCategory.objects.create(super_category=faq_super, name="Sharing & Activation", slug="sharing-activation")
        faq_page = SupportPage.objects.create(name="Campaign Sharing Page", slug="campaign-sharing-page", source_system="Customer support", source_flow="General support")
        generic_faq = SupportItem.objects.create(
            page=faq_page,
            category=faq_category,
            name="Doctor or clinic has not been added to the campaign",
            slug="doctor-or-clinic-has-not-been-added-to-the-campaign",
            knowledge_type=SupportItem.KnowledgeType.FAQ,
            solution_body="Capture the onboarding context and escalate to campaign operations.",
            source_system="Customer support",
            source_flow="General support",
            is_visible_to_brand_managers=True,
            is_visible_to_doctors=False,
            is_visible_to_clinic_staff=False,
            is_visible_to_field_reps=False,
        )

        response = self.client.post(
            reverse(
                "support_center:faq_page_other_issue",
                kwargs={"user_type": "brand_manager", "page_slug": faq_page.slug},
            ),
            data={
                "requester_name": "Brand Manager",
                "requester_email": "brand.manager@example.com",
                "requester_number": "+913333333333",
                "free_text": "Testing the chat from the In-clinic system.",
                "uploaded_file": SimpleUploadedFile("contact.jpg", b"image-bytes", content_type="image/jpeg"),
                "selected_faq_id": generic_faq.pk,
                "selected_section_slug": faq_super.slug,
                "source_system": "In-clinic",
                "source_flow": "Campaign Operations",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])

        support_request = SupportRequest.objects.get(pk=payload["request_id"])
        self.assertEqual(support_request.source_system, "In-clinic")
        self.assertEqual(support_request.source_flow, "Campaign Operations")
        self.assertEqual(support_request.requester_number, "+913333333333")
        self.assertTrue(support_request.uploaded_file.name.endswith(".jpg"))

    def test_widget_other_issue_preserves_query_context_for_shared_faq_groups(self):
        faq_super = SupportSuperCategory.objects.create(name="Shared Context Tests", slug="shared-context-tests")
        faq_category = SupportCategory.objects.create(super_category=faq_super, name="Sharing & Activation", slug="sharing-activation")
        faq_page = SupportPage.objects.create(name="Shared Context Page", slug="shared-context-page", source_system="Customer support", source_flow="General support")
        generic_faq = SupportItem.objects.create(
            page=faq_page,
            category=faq_category,
            name="Doctor or clinic has not been added to the campaign",
            slug="doctor-or-clinic-has-not-been-added-to-the-campaign",
            knowledge_type=SupportItem.KnowledgeType.FAQ,
            solution_body="Capture the onboarding context and escalate to campaign operations.",
            source_system="Customer support",
            source_flow="General support",
            is_visible_to_brand_managers=True,
            is_visible_to_doctors=False,
            is_visible_to_clinic_staff=False,
            is_visible_to_field_reps=False,
        )

        api_response = self.client.get(
            reverse(
                "support_center:faq_page_api",
                kwargs={"user_type": "brand_manager", "page_slug": faq_page.slug},
            ),
            data={"system": "In-clinic", "flow": "Campaign Operations"},
        )
        self.assertEqual(api_response.status_code, 200)
        api_payload = api_response.json()
        self.assertEqual(api_payload["source_system"], "In-clinic")
        self.assertEqual(api_payload["source_flow"], "Campaign Operations")
        self.assertTrue(api_payload["other_issue_url"].startswith("/support/"))
        self.assertNotIn("http://", api_payload["other_issue_url"])
        self.assertIn("system=In-clinic", api_payload["other_issue_url"])
        self.assertIn("flow=Campaign+Operations", api_payload["other_issue_url"])

        response = self.client.post(
            f"{reverse('support_center:faq_page_other_issue', kwargs={'user_type': 'brand_manager', 'page_slug': faq_page.slug})}?system=In-clinic&flow=Campaign+Operations",
            data={
                "requester_name": "Campaign Project Manager",
                "requester_email": "campaignpm@inditech.co.in",
                "requester_number": "+914444444444",
                "free_text": "Testing the shared FAQ widget from the In-clinic system.",
                "uploaded_file": SimpleUploadedFile("ku.png", b"image-bytes", content_type="image/png"),
                "selected_faq_id": generic_faq.pk,
                "selected_section_slug": faq_super.slug,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])

        support_request = SupportRequest.objects.get(pk=payload["request_id"])
        self.assertEqual(support_request.source_system, "In-clinic")
        self.assertEqual(support_request.source_flow, "Campaign Operations")
        self.assertEqual(support_request.requester_number, "+914444444444")
        self.assertTrue(support_request.uploaded_file.name.endswith(".png"))

    def test_widget_embed_uses_relative_other_issue_url_to_avoid_mixed_content(self):
        faq_super = SupportSuperCategory.objects.create(name="HTTPS Widget Tests", slug="https-widget-tests")
        faq_category = SupportCategory.objects.create(super_category=faq_super, name="Doctor Sharing", slug="doctor-sharing")
        faq_page = SupportPage.objects.create(
            name="Doctor / Clinic Sharing Page",
            slug="doctor-clinic-sharing-page",
            source_system="Patient Education",
            source_flow="Flow1 / Doctor",
        )
        SupportItem.objects.create(
            page=faq_page,
            category=faq_category,
            name="Share with patient issue",
            slug="share-with-patient-issue",
            knowledge_type=SupportItem.KnowledgeType.FAQ,
            solution_body="Use the sharing troubleshooting steps.",
            source_system="Patient Education",
            source_flow="Flow1 / Doctor",
            is_visible_to_doctors=True,
            is_visible_to_clinic_staff=False,
            is_visible_to_brand_managers=False,
            is_visible_to_field_reps=False,
            is_visible_to_patients=False,
        )

        widget_url = reverse(
            "support_center:faq_page_widget",
            kwargs={"user_type": "doctor", "page_slug": faq_page.slug},
        )
        response = self.client.get(
            f"{widget_url}?system=Patient+Education&flow=Flow1+%2F+Doctor&embed=1",
            secure=True,
            HTTP_X_FORWARDED_PROTO="https",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/support/doctor/faq/page/doctor-clinic-sharing-page/other/")
        self.assertContains(response, "system=Patient+Education")
        self.assertContains(response, "flow=Flow1+%2F+Doctor")
        self.assertNotContains(response, "http://testserver/support/doctor/faq/page/doctor-clinic-sharing-page/other/")

    @override_settings(EXTERNAL_TICKETING_SYNC_ENABLED=False)
    def test_pm_can_raise_ticket_from_other_issue_submission(self):
        support_page = SupportPage.objects.create(name="Collateral Viewer Page", slug="collateral-viewer-page", source_system="In-clinic", source_flow="Content Viewing")
        support_super = SupportSuperCategory.objects.create(name="Content Viewing", slug="content-viewing")
        support_category = SupportCategory.objects.create(super_category=support_super, name="Collateral Viewer Screen", slug="collateral-viewer-screen")
        support_request = SupportRequest.objects.create(
            user_type="doctor",
            requester_name="Doctor support user",
            requester_email="doctor.widget@support-widget.local",
            requester_number="+915555555555",
            requester_company="",
            campaign=self.campaign,
            support_page=support_page,
            support_super_category=support_super,
            support_category=support_category,
            source_system="In-clinic",
            source_flow="Content Viewing",
            subject="Other issue - Collateral Viewer",
            free_text="The viewer is opening a blank white screen after verification.",
            uploaded_file=SimpleUploadedFile("viewer.png", b"image-bytes", content_type="image/png"),
            status=SupportRequest.Status.PENDING_PM_REVIEW,
        )

        self.client.force_login(self.pm_user)
        dashboard_response = self.client.get(reverse("dashboards:home"))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, "Other Issues")
        self.assertContains(dashboard_response, "The viewer is opening a blank white screen after verification.")
        self.assertContains(dashboard_response, support_request.queue_ticket_number)
        self.assertContains(dashboard_response, "Doctor support user")
        self.assertContains(dashboard_response, "+915555555555")

        raise_url = reverse("support_center:raise_ticket", kwargs={"request_id": support_request.pk})
        raise_page = self.client.get(raise_url)
        self.assertEqual(raise_page.status_code, 200)
        self.assertContains(raise_page, "Raise ticket from support issue")
        self.assertContains(raise_page, "This file will be attached to the created ticket automatically.")
        self.assertContains(raise_page, "viewer.png")
        self.assertContains(raise_page, "Collateral Viewer Page")
        self.assertContains(raise_page, "+915555555555")

        category = TicketCategory.objects.get(name="Support")
        ticket_type = TicketTypeDefinition.objects.get(category=category, name="Query")
        response = self.client.post(
            raise_url,
            data={
                "title": "Viewer blank screen after verification",
                "description": "The viewer is opening a blank white screen after verification.\n\nEscalated from the PM dashboard.",
                "ticket_category": category.pk,
                "ticket_type_definition": ticket_type.pk,
                "new_ticket_type_name": "",
                "user_type": Ticket.UserType.DOCTOR,
                "source_system": Ticket.SourceSystem.IN_CLINIC,
                "priority": Ticket.Priority.HIGH,
                "status": Ticket.Status.NOT_STARTED,
                "department": self.ticket.department.pk,
                "campaign": self.campaign.pk,
                "requester_name": "Doctor support user",
                "requester_email": "doctor.widget@support-widget.local",
                "requester_number": "+919999999999",
                "requester_company": "Clinic A",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        support_request.refresh_from_db()
        self.assertEqual(support_request.status, SupportRequest.Status.TICKET_CREATED)
        created_ticket = Ticket.objects.get(support_request=support_request)
        self.assertEqual(created_ticket.title, "Viewer blank screen after verification")
        self.assertTrue(TicketNote.objects.filter(ticket=created_ticket, body__icontains="support widget").exists())
        self.assertTrue(TicketAttachment.objects.filter(note__ticket=created_ticket).exists())

    @patch("apps.dashboards.services.requests.get")
    @override_settings(EXTERNAL_TICKETING_SYNC_ENABLED=False)
    def test_pm_support_issue_views_render_timestamps_in_india_time(self, mock_get):
        mock_get.return_value = Mock(status_code=200)
        utc_zone = ZoneInfo("UTC")
        support_page = SupportPage.objects.create(name="Timezone Support Page", slug="timezone-support-page", source_system="In-clinic", source_flow="Timezone Flow")
        support_super = SupportSuperCategory.objects.create(name="Timezone Section", slug="timezone-section")
        support_category = SupportCategory.objects.create(super_category=support_super, name="Timezone Screen", slug="timezone-screen")
        support_request = SupportRequest.objects.create(
            user_type="doctor",
            requester_name="Doctor timezone user",
            requester_email="doctor.timezone@example.com",
            requester_number="+919898989898",
            requester_company="Clinic A",
            campaign=self.campaign,
            support_page=support_page,
            support_super_category=support_super,
            support_category=support_category,
            source_system="In-clinic",
            source_flow="Timezone Flow",
            subject="Other issue - Timezone",
            free_text="The support timestamps should follow India time.",
            status=SupportRequest.Status.PENDING_PM_REVIEW,
        )
        SupportRequest.objects.filter(pk=support_request.pk).update(created_at=datetime(2026, 1, 1, 6, 0, tzinfo=utc_zone))

        self.client.force_login(self.pm_user)
        dashboard_response = self.client.get(reverse("dashboards:home"))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, "01 Jan 2026 11:30")
        self.assertNotContains(dashboard_response, "01 Jan 2026 06:00")

        raise_ticket_response = self.client.get(reverse("support_center:raise_ticket", kwargs={"request_id": support_request.pk}))
        self.assertEqual(raise_ticket_response.status_code, 200)
        self.assertContains(raise_ticket_response, "01 Jan 2026 11:30")


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


class SupportPdfImportCommandTests(TestCase):
    def test_import_support_pdfs_loads_new_rfa_publisher_and_brand_manager_flows(self):
        base_dir = Path(settings.BASE_DIR)
        publisher_pdf = base_dir / "static" / "support-pdfs" / "red-flag-alert-flow4-publisher-faqs.pdf"
        brand_manager_pdf = base_dir / "static" / "support-pdfs" / "red-flag-alert-flow5-brand-manager-faqs.pdf"

        call_command("import_support_pdfs", "--replace", str(publisher_pdf), str(brand_manager_pdf))

        publisher_items = SupportItem.objects.filter(
            source_system="Red Flag Alert",
            source_flow="Flow4 / Publisher",
            is_visible_to_publishers=True,
        )
        brand_manager_items = SupportItem.objects.filter(
            source_system="Red Flag Alert",
            source_flow="Flow5 / BrandManager",
            is_visible_to_brand_managers=True,
        )

        self.assertTrue(publisher_items.exists())
        self.assertTrue(brand_manager_items.exists())
        self.assertEqual(
            publisher_items.first().associated_pdf_url,
            "/static/support-pdfs/red-flag-alert-flow4-publisher-faqs.pdf",
        )
        self.assertEqual(
            brand_manager_items.first().associated_pdf_url,
            "/static/support-pdfs/red-flag-alert-flow5-brand-manager-faqs.pdf",
        )

        response = self.client.get(reverse("support_center:faq_links_api", kwargs={"user_type": "publisher"}))
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["role_title"], "Publisher Support")


class TicketingDropdownSeedCommandTests(TestCase):
    def test_seed_ticketing_dropdowns_creates_ticket_form_dependencies(self):
        call_command("seed_ticketing_dropdowns")

        self.assertGreaterEqual(Department.objects.count(), 3)
        self.assertGreaterEqual(TicketCategory.objects.count(), 9)
        self.assertGreaterEqual(TicketTypeDefinition.objects.count(), 22)
        self.assertGreaterEqual(Campaign.objects.count(), 3)


@override_settings(
    EXTERNAL_TICKETING_SYNC_ENABLED=True,
    EXTERNAL_TICKETING_BASE_URL="https://support.inditech.co.in",
    EXTERNAL_TICKETING_API_TOKEN="",
    EXTERNAL_TICKETING_REQUESTER_PHONE_FALLBACK="+919876543210",
)
class ExternalTicketSyncTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo_data")
        cls.pm_user = User.objects.get(email=settings.PROJECT_MANAGER_EMAIL)
        cls.pm_user.phone_number = "+919876543210"
        cls.pm_user.save(update_fields=["phone_number"])
        cls.department = Department.objects.get(code="TECH")
        cls.campaign = Campaign.objects.get(slug="cardioplus-unified-care")

    def _json_response(self, payload, *, status_code=200):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = payload
        return response

    @patch("apps.ticketing.external_ticketing.requests.request")
    @patch("apps.ticketing.external_ticketing.requests.get")
    def test_ticket_creation_syncs_to_external_department_manager(self, mock_get, mock_request):
        mock_get.return_value = self._json_response({}, status_code=404)

        def request_side_effect(method, url, headers=None, params=None, json=None, timeout=None):
            self.assertNotIn("X-Client-Ticket-Token", headers or {})
            if method == "GET" and url.endswith("/client-tickets/api/lookups/departments/"):
                return self._json_response(
                    {
                        "success": True,
                        "departments": [
                            {
                                "id": 3,
                                "name": "IT Support",
                                "code": "IT_SUPPORT",
                                "manager_id": 19,
                                "manager_name": "Tech Manager",
                                "manager_email": "tech.manager@inditech.co.in",
                                "is_active": True,
                            }
                        ],
                    }
                )
            if method == "GET" and url.endswith("/client-tickets/api/lookups/system-directory/"):
                return self._json_response(
                    {
                        "success": True,
                        "departments": [
                            {
                                "id": 3,
                                "name": "IT Support",
                                "code": "IT_SUPPORT",
                                "manager_id": None,
                                "manager_name": "",
                                "manager_email": "",
                                "is_active": True,
                            }
                        ],
                        "department_managers": [
                            {
                                "department_id": 3,
                                "department_name": "IT Support",
                                "department_code": "IT_SUPPORT",
                                "manager_id": 19,
                                "manager_name": "Tech Manager",
                                "manager_email": "tech.manager@inditech.co.in",
                            }
                        ],
                        "users": [
                            {
                                "id": 19,
                                "full_name": "Tech Manager",
                                "email": "tech.manager@inditech.co.in",
                                "department_id": 3,
                                "department_name": "IT Support",
                                "is_active": True,
                            }
                        ],
                    }
                )
            if method == "GET" and url.endswith("/client-tickets/api/lookups/ticket-types/"):
                return self._json_response(
                    {
                        "success": True,
                        "ticket_types": [
                            {
                                "id": 12,
                                "name": "System Down",
                                "department_id": 3,
                                "department_name": "Technical Support",
                                "is_active": True,
                            }
                        ],
                    }
                )
            if method == "POST" and url.endswith("/client-tickets/api/tickets/"):
                self.assertEqual(json["assigned_to_email"], "tech.manager@inditech.co.in")
                self.assertEqual(json["project_manager_email"], settings.PROJECT_MANAGER_EMAIL)
                self.assertEqual(json["department_id"], 3)
                self.assertEqual(json["ticket_type_id"], 12)
                self.assertEqual(json["source_system"], "campaign_management")
                self.assertEqual(json["priority"], "urgent")
                return self._json_response(
                    {
                        "success": True,
                        "ticket": {
                            "ticket_number": "CLT-8F3A1B2C",
                            "ticket_url": "https://support.inditech.co.in/client-tickets/tickets/CLT-8F3A1B2C/",
                            "status_code": "open",
                        },
                    }
                )
            raise AssertionError(f"Unexpected request {method} {url}")

        mock_request.side_effect = request_side_effect

        with self.captureOnCommitCallbacks(execute=True):
            ticket = create_ticket(
                title="Reports Site Down",
                description="Reporting site is returning 503.",
                ticket_type="System Down",
                user_type=Ticket.UserType.INTERNAL,
                source_system=Ticket.SourceSystem.PROJECT_MANAGER,
                priority=Ticket.Priority.CRITICAL,
                department=self.department,
                campaign=self.campaign,
                created_by=self.pm_user,
                submitted_by=self.pm_user,
                direct_recipient=self.department.default_recipient,
                current_assignee=self.department.default_recipient,
                requester_name="Campaign PM",
                requester_email=self.pm_user.email,
                requester_number=self.pm_user.phone_number,
                requester_company="Inditech",
            )

        ticket.refresh_from_db()
        self.department.refresh_from_db()
        self.assertEqual(ticket.external_ticket_number, "CLT-8F3A1B2C")
        self.assertEqual(ticket.external_ticket_status, "open")
        self.assertEqual(
            ticket.external_ticket_url,
            "https://support.inditech.co.in/client-tickets/tickets/CLT-8F3A1B2C/",
        )
        self.assertIsNotNone(ticket.external_ticket_synced_at)
        self.assertEqual(ticket.external_ticket_error, "")
        self.assertIn("Starting external ticket sync.", ticket.external_ticket_log)
        self.assertIn("Creating external ticket.", ticket.external_ticket_log)
        self.assertIn("External ticket created successfully.", ticket.external_ticket_log)
        self.assertEqual(self.department.default_recipient.email, "tech.manager@inditech.co.in")
        self.assertEqual(self.department.external_directory_name, "IT Support")
        self.assertEqual(self.department.external_directory_code, "IT_SUPPORT")

    @patch("apps.ticketing.external_ticketing.requests.request")
    @patch("apps.ticketing.external_ticketing.requests.get")
    def test_support_request_file_is_sent_to_external_ticket_create(self, mock_get, mock_request):
        mock_get.return_value = self._json_response({}, status_code=404)
        support_request = SupportRequest.objects.create(
            user_type="doctor",
            requester_name="Campaign PM",
            requester_email=self.pm_user.email,
            requester_number=self.pm_user.phone_number,
            requester_company="Inditech",
            campaign=self.campaign,
            source_system="Patient Education",
            source_flow="Flow1 / Doctor",
            subject="Other issue - Sharing page",
            free_text="Sharing page attachment should be mirrored to the internal ticket.",
            uploaded_file=SimpleUploadedFile("contact.jpg", b"image-bytes", content_type="image/jpeg"),
            status=SupportRequest.Status.PENDING_PM_REVIEW,
        )

        def request_side_effect(method, url, headers=None, params=None, json=None, timeout=None, data=None, files=None):
            self.assertNotIn("X-Client-Ticket-Token", headers or {})
            if method == "GET" and url.endswith("/client-tickets/api/lookups/departments/"):
                return self._json_response(
                    {
                        "success": True,
                        "departments": [
                            {
                                "id": 3,
                                "name": "IT Support",
                                "code": "IT_SUPPORT",
                                "manager_id": 19,
                                "manager_name": "Tech Manager",
                                "manager_email": "tech.manager@inditech.co.in",
                                "is_active": True,
                            }
                        ],
                    }
                )
            if method == "GET" and url.endswith("/client-tickets/api/lookups/system-directory/"):
                return self._json_response(
                    {
                        "success": True,
                        "departments": [
                            {
                                "id": 3,
                                "name": "IT Support",
                                "code": "IT_SUPPORT",
                                "manager_id": 19,
                                "manager_name": "Tech Manager",
                                "manager_email": "tech.manager@inditech.co.in",
                                "is_active": True,
                            }
                        ],
                        "department_managers": [],
                        "users": [
                            {
                                "id": 19,
                                "full_name": "Tech Manager",
                                "email": "tech.manager@inditech.co.in",
                                "department_id": 3,
                                "department_name": "IT Support",
                                "is_active": True,
                            }
                        ],
                    }
                )
            if method == "GET" and url.endswith("/client-tickets/api/lookups/ticket-types/"):
                return self._json_response(
                    {
                        "success": True,
                        "ticket_types": [
                            {
                                "id": 12,
                                "name": "System Down",
                                "department_id": 3,
                                "department_name": "Technical Support",
                                "is_active": True,
                            }
                        ],
                    }
                )
            if method == "POST" and url.endswith("/client-tickets/api/tickets/"):
                self.assertIsNone(json)
                self.assertEqual(data["assigned_to_email"], "tech.manager@inditech.co.in")
                self.assertEqual(data["project_manager_email"], settings.PROJECT_MANAGER_EMAIL)
                self.assertEqual(data["department_id"], 3)
                self.assertEqual(data["ticket_type_id"], 12)
                self.assertEqual(len(files), 1)
                field_name, file_tuple = files[0]
                filename, file_handle, content_type = file_tuple
                self.assertEqual(field_name, "attachments")
                self.assertEqual(filename, "contact.jpg")
                self.assertEqual(file_handle.read(), b"image-bytes")
                self.assertEqual(content_type, "image/jpeg")
                return self._json_response(
                    {
                        "success": True,
                        "ticket": {
                            "ticket_number": "CLT-8F3A1B2C",
                            "ticket_url": "https://support.inditech.co.in/client-tickets/tickets/CLT-8F3A1B2C/",
                            "status_code": "open",
                        },
                    }
                )
            raise AssertionError(f"Unexpected request {method} {url}")

        mock_request.side_effect = request_side_effect

        with self.captureOnCommitCallbacks(execute=True):
            ticket = create_ticket(
                title="Reports Site Down",
                description="Reporting site is returning 503.",
                ticket_type="System Down",
                user_type=Ticket.UserType.INTERNAL,
                source_system=Ticket.SourceSystem.PROJECT_MANAGER,
                priority=Ticket.Priority.CRITICAL,
                department=self.department,
                campaign=self.campaign,
                created_by=self.pm_user,
                submitted_by=self.pm_user,
                direct_recipient=self.department.default_recipient,
                current_assignee=self.department.default_recipient,
                requester_name="Campaign PM",
                requester_email=self.pm_user.email,
                requester_number=self.pm_user.phone_number,
                requester_company="Inditech",
                support_request=support_request,
            )

        ticket.refresh_from_db()
        self.assertEqual(ticket.external_ticket_number, "CLT-8F3A1B2C")
        self.assertEqual(ticket.external_ticket_error, "")

    @patch("apps.ticketing.external_ticketing.requests.request")
    def test_directory_sync_updates_local_department_manager_routing(self, mock_request):
        def request_side_effect(method, url, headers=None, params=None, json=None, timeout=None):
            self.assertNotIn("X-Client-Ticket-Token", headers or {})
            if method == "GET" and url.endswith("/client-tickets/api/lookups/departments/"):
                return self._json_response(
                    {
                        "success": True,
                        "departments": [
                            {
                                "id": 3,
                                "name": "IT Support",
                                "code": "IT_SUPPORT",
                                "manager_id": 19,
                                "manager_name": "Tech Manager",
                                "manager_email": "tech.manager@inditech.co.in",
                                "is_active": True,
                            }
                        ],
                    }
                )
            if method == "GET" and url.endswith("/client-tickets/api/lookups/system-directory/"):
                return self._json_response(
                    {
                        "success": True,
                        "departments": [
                            {
                                "id": 3,
                                "name": "IT Support",
                                "code": "IT_SUPPORT",
                                "manager_id": 19,
                                "manager_name": "Tech Manager",
                                "manager_email": "tech.manager@inditech.co.in",
                                "is_active": True,
                            }
                        ],
                        "department_managers": [],
                        "users": [
                            {
                                "id": 19,
                                "full_name": "Tech Manager",
                                "email": "tech.manager@inditech.co.in",
                                "department_id": 3,
                                "department_name": "IT Support",
                                "is_active": True,
                            }
                        ],
                    }
                )
            raise AssertionError(f"Unexpected request {method} {url}")

        mock_request.side_effect = request_side_effect

        synced_departments = sync_external_directory()
        self.assertEqual(len(synced_departments), 1)
        department = Department.objects.get(pk=self.department.pk)
        self.assertEqual(department.external_directory_id, 3)
        self.assertEqual(department.external_directory_name, "IT Support")
        self.assertEqual(department.external_directory_code, "IT_SUPPORT")
        self.assertEqual(department.external_manager_email, "tech.manager@inditech.co.in")
        self.assertEqual(department.default_recipient.email, "tech.manager@inditech.co.in")

    @patch("apps.ticketing.external_ticketing.requests.request")
    def test_ticket_create_page_uses_synced_internal_directory_departments(self, mock_request):
        def request_side_effect(method, url, headers=None, params=None, json=None, timeout=None):
            self.assertNotIn("X-Client-Ticket-Token", headers or {})
            if method == "GET" and url.endswith("/client-tickets/api/lookups/departments/"):
                return self._json_response(
                    {
                        "success": True,
                        "departments": [
                            {
                                "id": 3,
                                "name": "IT Support",
                                "code": "IT_SUPPORT",
                                "manager_id": 19,
                                "manager_name": "Tech Manager",
                                "manager_email": "tech.manager@inditech.co.in",
                                "is_active": True,
                            }
                        ],
                    }
                )
            if method == "GET" and url.endswith("/client-tickets/api/lookups/system-directory/"):
                return self._json_response(
                    {
                        "success": True,
                        "departments": [
                            {
                                "id": 3,
                                "name": "IT Support",
                                "code": "IT_SUPPORT",
                                "manager_id": 19,
                                "manager_name": "Tech Manager",
                                "manager_email": "tech.manager@inditech.co.in",
                                "is_active": True,
                            }
                        ],
                        "department_managers": [],
                        "users": [
                            {
                                "id": 19,
                                "full_name": "Tech Manager",
                                "email": "tech.manager@inditech.co.in",
                                "department_id": 3,
                                "department_name": "IT Support",
                                "is_active": True,
                            }
                        ],
                    }
                )
            raise AssertionError(f"Unexpected request {method} {url}")

        mock_request.side_effect = request_side_effect

        self.client.force_login(self.pm_user)
        response = self.client.get(reverse("ticketing:create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "IT Support - Auto route to Tech Manager")
        self.assertContains(response, self.pm_user.phone_number)

    @patch("apps.ticketing.external_ticketing.requests.request")
    def test_note_attachment_syncs_to_existing_external_ticket(self, mock_request):
        ticket = Ticket.objects.create(
            title="Reports Site Down",
            description="Reporting site is returning 503.",
            ticket_type="System Down",
            user_type=Ticket.UserType.INTERNAL,
            source_system=Ticket.SourceSystem.PROJECT_MANAGER,
            priority=Ticket.Priority.CRITICAL,
            status=Ticket.Status.NOT_STARTED,
            department=self.department,
            campaign=self.campaign,
            created_by=self.pm_user,
            submitted_by=self.pm_user,
            direct_recipient=self.department.default_recipient,
            current_assignee=self.department.default_recipient,
            requester_name="Campaign PM",
            requester_email=self.pm_user.email,
            requester_number=self.pm_user.phone_number,
            requester_company="Inditech",
            external_ticket_number="CLT-EXISTING",
            external_ticket_url="https://support.inditech.co.in/client-tickets/tickets/CLT-EXISTING/",
            external_ticket_status="open",
        )

        def request_side_effect(method, url, headers=None, params=None, json=None, timeout=None, data=None, files=None):
            self.assertNotIn("X-Client-Ticket-Token", headers or {})
            if method == "POST" and url.endswith("/client-tickets/api/tickets/CLT-EXISTING/inditech-update/"):
                self.assertIsNone(json)
                self.assertEqual(data["updated_by_email"], ticket.current_assignee.email)
                self.assertEqual(len(files), 1)
                field_name, file_tuple = files[0]
                filename, file_handle, content_type = file_tuple
                self.assertEqual(field_name, "attachments")
                self.assertEqual(filename, "note.txt")
                self.assertEqual(file_handle.read(), b"attachment")
                self.assertEqual(content_type, "text/plain")
                return self._json_response(
                    {
                        "success": True,
                        "ticket": {
                            "ticket_number": "CLT-EXISTING",
                            "status_code": "open",
                        },
                    }
                )
            raise AssertionError(f"Unexpected request {method} {url}")

        mock_request.side_effect = request_side_effect

        self.client.force_login(ticket.current_assignee)
        response = self.client.post(
            reverse("ticketing:detail", kwargs={"pk": ticket.pk}),
            data={
                "action": "note",
                "body": "Added a diagnostic note from test coverage.",
                "attachments": SimpleUploadedFile("note.txt", b"attachment", content_type="text/plain"),
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.external_ticket_error, "")
        self.assertIn("External ticket attachments synced successfully.", ticket.external_ticket_log)

    @patch("apps.ticketing.external_ticketing.requests.get")
    @patch("apps.dashboards.services.requests.get")
    def test_pm_dashboard_refreshes_mirrored_ticket_state_from_external_system(self, mock_status_get, mock_external_get):
        mock_status_get.return_value = Mock(status_code=200)
        ticket = Ticket.objects.create(
            title="External sync state check",
            description="State changes should sync from Inditech ticketing.",
            ticket_type="System Down",
            user_type=Ticket.UserType.INTERNAL,
            source_system=Ticket.SourceSystem.PROJECT_MANAGER,
            priority=Ticket.Priority.HIGH,
            status=Ticket.Status.NOT_STARTED,
            department=self.department,
            campaign=self.campaign,
            created_by=self.pm_user,
            submitted_by=self.pm_user,
            direct_recipient=self.department.default_recipient,
            current_assignee=self.department.default_recipient,
            requester_name="Campaign PM",
            requester_email=self.pm_user.email,
            requester_number=self.pm_user.phone_number,
            requester_company="Inditech",
            external_ticket_number="CLT-72E24C64",
            external_ticket_url="https://support.inditech.co.in/client-tickets/tickets/CLT-72E24C64/",
            external_ticket_status="open",
        )
        mock_external_get.return_value = self._json_response(
            {
                "success": True,
                "ticket": {
                    "ticket_number": "CLT-72E24C64",
                    "ticket_url": "https://support.inditech.co.in/client-tickets/tickets/CLT-72E24C64/",
                    "status_code": "in_progress",
                    "assigned_to_email": "queue.owner@inditech.co.in",
                    "assigned_to_name": "Queue Owner",
                },
            }
        )

        self.client.force_login(self.pm_user)
        response = self.client.get(reverse("dashboards:home"))

        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.IN_PROCESS)
        self.assertEqual(ticket.external_ticket_status, "in_progress")
        self.assertEqual(ticket.current_assignee.email, "queue.owner@inditech.co.in")
        self.assertContains(response, "Queue Owner")
        self.assertContains(response, "In process")

    @patch("apps.ticketing.external_ticketing.requests.get")
    def test_mirrored_ticket_detail_is_read_only_and_refreshes_from_external_system(self, mock_external_get):
        ticket = Ticket.objects.create(
            title="External read only check",
            description="Mirrored tickets should be managed from Inditech ticketing.",
            ticket_type="System Down",
            user_type=Ticket.UserType.INTERNAL,
            source_system=Ticket.SourceSystem.PROJECT_MANAGER,
            priority=Ticket.Priority.HIGH,
            status=Ticket.Status.NOT_STARTED,
            department=self.department,
            campaign=self.campaign,
            created_by=self.pm_user,
            submitted_by=self.pm_user,
            direct_recipient=self.department.default_recipient,
            current_assignee=self.department.default_recipient,
            requester_name="Campaign PM",
            requester_email=self.pm_user.email,
            requester_number=self.pm_user.phone_number,
            requester_company="Inditech",
            external_ticket_number="CLT-READONLY",
            external_ticket_url="https://support.inditech.co.in/client-tickets/tickets/CLT-READONLY/",
            external_ticket_status="open",
        )
        mock_external_get.return_value = self._json_response(
            {
                "success": True,
                "ticket": {
                    "ticket_number": "CLT-READONLY",
                    "ticket_url": "https://support.inditech.co.in/client-tickets/tickets/CLT-READONLY/",
                    "status_code": "closed",
                    "assigned_to_email": "closed.owner@inditech.co.in",
                    "assigned_to_name": "Closed Owner",
                },
            }
        )

        self.client.force_login(self.pm_user)
        response = self.client.get(reverse("ticketing:detail", kwargs={"pk": ticket.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ticket management")
        self.assertContains(response, "synced internal ticketing system")
        self.assertNotContains(response, "Manage in Inditech ticketing")
        self.assertContains(response, "Closed Owner")
        self.assertNotContains(response, "Change status")
        self.assertNotContains(response, "Delegate ticket")
        self.assertNotContains(response, "Return to sender")
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.COMPLETED)
        self.assertEqual(ticket.current_assignee.email, "closed.owner@inditech.co.in")

    @patch("apps.dashboards.services.requests.get")
    @override_settings(EXTERNAL_TICKETING_SYNC_ENABLED=False)
    def test_pm_dashboard_prioritizes_escalated_queue_tickets(self, mock_get):
        mock_get.return_value = Mock(status_code=200)
        support_page = SupportPage.objects.create(name="Queue Order Page", slug="queue-order-page", source_system="In-clinic", source_flow="Queue Order")
        support_super = SupportSuperCategory.objects.create(name="Queue Order Section", slug="queue-order-section")
        support_category = SupportCategory.objects.create(super_category=support_super, name="Queue Order Screen", slug="queue-order-screen")
        escalated_request = SupportRequest.objects.create(
            user_type="doctor",
            requester_name="Escalated User",
            requester_email="escalated@example.com",
            requester_number="+917777777777",
            device_type="android",
            device="phone",
            support_page=support_page,
            support_super_category=support_super,
            support_category=support_category,
            source_system="In-clinic",
            source_flow="Queue Order",
            subject="Other issue - escalated",
            free_text="This should appear first.",
            status=SupportRequest.Status.PENDING_PM_REVIEW,
            is_escalated=True,
        )
        standard_request = SupportRequest.objects.create(
            user_type="doctor",
            requester_name="Standard User",
            requester_email="standard@example.com",
            requester_number="+916666666665",
            device_type="ios",
            device="tablet",
            support_page=support_page,
            support_super_category=support_super,
            support_category=support_category,
            source_system="In-clinic",
            source_flow="Queue Order",
            subject="Other issue - standard",
            free_text="This should appear second.",
            status=SupportRequest.Status.PENDING_PM_REVIEW,
        )

        self.client.force_login(self.pm_user)
        response = self.client.get(reverse("dashboards:home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertLess(content.index(escalated_request.queue_ticket_number), content.index(standard_request.queue_ticket_number))
        self.assertContains(response, "High Priority / Escalated")
        self.assertContains(response, "Escalated User")
        self.assertContains(response, "+917777777777")
        self.assertContains(response, "Android")
        self.assertContains(response, "Phone")
        self.assertNotContains(
            response,
            reverse("support_center:escalate_request", kwargs={"request_id": escalated_request.pk}),
            html=False,
        )
        self.assertNotContains(
            response,
            reverse("support_center:escalate_request", kwargs={"request_id": standard_request.pk}),
            html=False,
        )

    @patch("apps.dashboards.services.requests.get")
    @override_settings(EXTERNAL_TICKETING_SYNC_ENABLED=False)
    def test_other_issue_queue_endpoint_requires_ticket_before_escalation(self, mock_get):
        mock_get.return_value = Mock(status_code=200)
        support_request = SupportRequest.objects.create(
            user_type="doctor",
            requester_name="Queue User",
            requester_email="queue-user@example.com",
            requester_number="+917700000000",
            subject="Other issue - queue",
            free_text="Please review this queue request.",
            status=SupportRequest.Status.PENDING_PM_REVIEW,
        )

        self.client.force_login(self.pm_user)
        response = self.client.post(
            reverse("support_center:escalate_request", kwargs={"request_id": support_request.pk}),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        support_request.refresh_from_db()
        self.assertFalse(support_request.is_escalated)
        self.assertContains(
            response,
            f"{support_request.queue_ticket_number} cannot be escalated from Other Issues. Raise a ticket and mark it Critical first.",
        )

    @patch("apps.ticketing.external_ticketing.requests.request")
    def test_support_issue_raise_ticket_page_uses_synced_internal_directory_departments(self, mock_request):
        support_request = SupportRequest.objects.create(
            user_type="doctor",
            requester_name="Doctor support user",
            requester_email="doctor.widget@support-widget.local",
            requester_company="Clinic A",
            campaign=self.campaign,
            support_category=SupportCategory.objects.first(),
            source_system="In-clinic",
            source_flow="Content Viewing",
            subject="Other issue - Collateral Viewer",
            free_text="The viewer is opening a blank white screen after verification.",
            status=SupportRequest.Status.PENDING_PM_REVIEW,
        )

        def request_side_effect(method, url, headers=None, params=None, json=None, timeout=None):
            self.assertNotIn("X-Client-Ticket-Token", headers or {})
            if method == "GET" and url.endswith("/client-tickets/api/lookups/departments/"):
                return self._json_response(
                    {
                        "success": True,
                        "departments": [
                            {
                                "id": 3,
                                "name": "IT Support",
                                "code": "IT_SUPPORT",
                                "manager_id": 19,
                                "manager_name": "Tech Manager",
                                "manager_email": "tech.manager@inditech.co.in",
                                "is_active": True,
                            }
                        ],
                    }
                )
            if method == "GET" and url.endswith("/client-tickets/api/lookups/system-directory/"):
                return self._json_response(
                    {
                        "success": True,
                        "departments": [
                            {
                                "id": 3,
                                "name": "IT Support",
                                "code": "IT_SUPPORT",
                                "manager_id": 19,
                                "manager_name": "Tech Manager",
                                "manager_email": "tech.manager@inditech.co.in",
                                "is_active": True,
                            }
                        ],
                        "department_managers": [],
                        "users": [
                            {
                                "id": 19,
                                "full_name": "Tech Manager",
                                "email": "tech.manager@inditech.co.in",
                                "department_id": 3,
                                "department_name": "IT Support",
                                "is_active": True,
                            }
                        ],
                    }
                )
            raise AssertionError(f"Unexpected request {method} {url}")

        mock_request.side_effect = request_side_effect

        self.client.force_login(self.pm_user)
        response = self.client.get(reverse("support_center:raise_ticket", kwargs={"request_id": support_request.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "IT Support - Auto route to Tech Manager")
