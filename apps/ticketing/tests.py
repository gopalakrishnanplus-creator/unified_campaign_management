import json
from unittest.mock import Mock, patch

from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.ticketing.models import Department, SpecialInstructionReview, Ticket
from apps.ticketing.special_instructions import create_or_update_special_instruction_review


@override_settings(
    REPORTING_API_USE_LIVE=False,
    EXTERNAL_TICKETING_SYNC_ENABLED=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SENDGRID_API_KEY="",
    SPECIAL_INSTRUCTION_BASE_URL="https://red-flag-alerts.co.in",
    SPECIAL_INSTRUCTION_PM_API_TOKEN="test-token",
)
class SpecialInstructionWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo_data")
        cls.pm_user = User.objects.get(email=settings.PROJECT_MANAGER_EMAIL)
        cls.special_instruction_assignee = Department.objects.get(code="PRODUCT").default_recipient
        cls.assignee = Department.objects.get(code="TECHNOLOGY").default_recipient

    def _payload(self):
        return {
            "ok": True,
            "ticket": {
                "doctor": {
                    "id": "DOC401",
                    "name": "Dr. Portal Doctor",
                    "email": "portal@example.com",
                },
                "clinic": {
                    "name": "Clinic Portal",
                    "phone": "9876543210",
                },
                "associated_campaign": {
                    "campaign_id": "campaign-uuid",
                    "campaign_name": "Growth Campaign",
                    "brand_name": "Pedia",
                    "field_rep": {
                        "id": "FR001",
                        "internal_id": 12,
                        "name": "Rep One",
                    },
                },
                "assigned_field_rep": {
                    "id": "FR001",
                    "internal_id": 12,
                    "name": "Rep One",
                },
                "special_instruction": {
                    "current_status": "Document in process",
                    "status_code": "in_process",
                    "uploaded_at": "2026-05-06T10:30:00+00:00",
                    "download_url": "https://red-flag-alerts.co.in/internal/special-instructions/DOC401/download/",
                    "approve_url": "https://red-flag-alerts.co.in/internal/special-instructions/DOC401/approve/",
                },
            },
        }

    def _json_response(self, payload, *, status_code=200, url="https://red-flag-alerts.co.in/test/"):
        response = Mock()
        response.status_code = status_code
        response.url = url
        response.json.return_value = payload
        response.headers = {"Content-Type": "application/json"}
        response.content = b""
        return response

    @patch("apps.ticketing.special_instructions.requests.request")
    def test_pm_fetches_rfa_payload_into_review_ticket(self, mock_request):
        def request_side_effect(method, url, headers=None, params=None, timeout=None, **kwargs):
            self.assertEqual(method, "GET")
            self.assertTrue(url.endswith("/internal/special-instructions/DOC401/ticket/"))
            self.assertEqual(params, {"campaign_id": "campaign-uuid"})
            self.assertEqual(headers["Authorization"], "Bearer test-token")
            return self._json_response(self._payload(), url=url)

        mock_request.side_effect = request_side_effect

        self.client.force_login(self.pm_user)
        response = self.client.post(
            reverse("dashboards:special_instruction_fetch"),
            data={"doctor_id": "DOC401", "campaign_id": "campaign-uuid"},
        )

        review = SpecialInstructionReview.objects.select_related("ticket").get(doctor_id="DOC401")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("ticketing:detail", kwargs={"pk": review.ticket.pk}))
        self.assertEqual(review.source_reference, "DOC401:campaign-uuid")
        self.assertEqual(review.clinic_name, "Clinic Portal")
        self.assertEqual(review.campaign_name, "Growth Campaign")
        self.assertEqual(review.assigned_field_rep_name, "Rep One")
        self.assertEqual(review.rfa_current_status, "Document in process")
        self.assertEqual(review.ticket.source_system, Ticket.SourceSystem.RED_FLAG_ALERT)
        self.assertEqual(review.ticket.ticket_type, "Special Instruction Approval")
        self.assertEqual(review.ticket.department.code, "PRODUCT")
        self.assertEqual(review.ticket.current_assignee, self.special_instruction_assignee)
        self.assertEqual(review.ticket.direct_recipient, self.special_instruction_assignee)
        self.assertEqual(review.ticket.external_ticket_number, "")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.special_instruction_assignee.email])

        second_response = self.client.post(
            reverse("dashboards:special_instruction_fetch"),
            data={"doctor_id": "DOC401", "campaign_id": "campaign-uuid"},
        )
        review.refresh_from_db()
        self.assertEqual(second_response.status_code, 302)
        self.assertEqual(SpecialInstructionReview.objects.filter(doctor_id="DOC401").count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_rfa_webhook_creates_review_ticket_without_manual_pm_fetch(self):
        response = self.client.post(
            reverse("dashboards:special_instruction_webhook"),
            data=json.dumps(self._payload()),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        self.assertEqual(response.status_code, 200)
        response_payload = response.json()
        self.assertTrue(response_payload["success"])
        self.assertEqual(response_payload["doctor_id"], "DOC401")
        review = SpecialInstructionReview.objects.select_related("ticket").get(doctor_id="DOC401")
        self.assertEqual(response_payload["ticket_number"], review.ticket.ticket_number)
        self.assertEqual(response_payload["assignee_email"], self.special_instruction_assignee.email)
        self.assertIn(reverse("ticketing:detail", kwargs={"pk": review.ticket.pk}), response_payload["ticket_url"])
        self.assertEqual(review.ticket.department.code, "PRODUCT")
        self.assertEqual(review.ticket.current_assignee, self.special_instruction_assignee)
        self.assertEqual(review.rfa_current_status, "Document in process")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.special_instruction_assignee.email])

        self.client.force_login(self.pm_user)
        dashboard_response = self.client.get(reverse("dashboards:home"))
        self.assertContains(dashboard_response, "Doctor ID DOC401")
        self.assertContains(dashboard_response, "Document approval queue")
        self.assertContains(dashboard_response, "Assigned")

    def test_rfa_webhook_accepts_wrapped_payload_without_trailing_slash(self):
        response = self.client.post(
            reverse("dashboards:special_instruction_webhook").rstrip("/"),
            data=json.dumps({"data": self._payload()}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        review = SpecialInstructionReview.objects.select_related("ticket").get(doctor_id="DOC401")
        self.assertEqual(response.json()["ticket_number"], review.ticket.ticket_number)

    @patch("apps.ticketing.special_instructions.requests.request")
    def test_rfa_webhook_can_fetch_payload_from_doctor_id(self, mock_request):
        def request_side_effect(method, url, headers=None, params=None, timeout=None, **kwargs):
            self.assertEqual(method, "GET")
            self.assertTrue(url.endswith("/internal/special-instructions/DOC401/ticket/"))
            self.assertEqual(params, {"campaign_id": "campaign-uuid"})
            return self._json_response(self._payload(), url=url)

        mock_request.side_effect = request_side_effect

        response = self.client.post(
            reverse("dashboards:special_instruction_webhook"),
            data=json.dumps({"doctor_id": "DOC401", "campaign_id": "campaign-uuid"}),
            content_type="application/json",
            HTTP_X_SPECIAL_INSTRUCTION_TOKEN="test-token",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertTrue(SpecialInstructionReview.objects.filter(doctor_id="DOC401").exists())

    @patch("apps.ticketing.special_instructions.requests.request")
    def test_rfa_webhook_accepts_form_encoded_doctor_id(self, mock_request):
        def request_side_effect(method, url, headers=None, params=None, timeout=None, **kwargs):
            self.assertEqual(method, "GET")
            self.assertTrue(url.endswith("/internal/special-instructions/DOC401/ticket/"))
            self.assertEqual(params, {"campaign_id": "campaign-uuid"})
            return self._json_response(self._payload(), url=url)

        mock_request.side_effect = request_side_effect

        response = self.client.post(
            reverse("dashboards:special_instruction_webhook"),
            data={"doctor_id": "DOC401", "campaign_id": "campaign-uuid"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertTrue(SpecialInstructionReview.objects.filter(doctor_id="DOC401").exists())

    def test_rfa_webhook_rejects_missing_token(self):
        response = self.client.post(
            reverse("dashboards:special_instruction_webhook"),
            data=json.dumps(self._payload()),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(SpecialInstructionReview.objects.filter(doctor_id="DOC401").exists())

    def test_assigning_special_instruction_ticket_sends_download_and_approve_email(self):
        review = create_or_update_special_instruction_review(self._payload(), actor=self.pm_user)

        self.client.force_login(self.pm_user)
        response = self.client.post(
            reverse("ticketing:detail", kwargs={"pk": review.ticket.pk}),
            data={"action": "delegate", "assignee": self.assignee.pk},
            follow=True,
        )

        review.ticket.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(review.ticket.current_assignee, self.assignee)
        self.assertContains(response, "Special Instruction review assigned and email sent.")
        self.assertContains(response, "Assign reviewer")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.assignee.email])
        self.assertIn("DOC401", message.subject)
        self.assertIn("Clinic Portal", message.body)
        self.assertIn("Dr. Portal Doctor", message.body)
        self.assertIn("Growth Campaign", message.body)
        self.assertIn(reverse("ticketing:special_instruction_download", kwargs={"pk": review.ticket.pk}), message.body)
        self.assertIn(reverse("ticketing:special_instruction_approve", kwargs={"pk": review.ticket.pk}), message.body)
        self.assertIn("Download", message.alternatives[0][0])
        self.assertIn("Approve", message.alternatives[0][0])

    @patch("apps.dashboards.services.requests.get")
    @patch("apps.ticketing.special_instructions.requests.request")
    def test_download_and_approve_are_proxied_to_rfa_and_dashboard_card_updates(self, mock_request, mock_status_get):
        mock_status_get.return_value = Mock(status_code=200)
        review = create_or_update_special_instruction_review(self._payload(), actor=self.pm_user)

        def request_side_effect(method, url, headers=None, timeout=None, stream=False, **kwargs):
            self.assertEqual(headers["Authorization"], "Bearer test-token")
            if method == "GET" and url.endswith("/internal/special-instructions/DOC401/download/"):
                response = Mock()
                response.status_code = 200
                response.url = url
                response.headers = {
                    "Content-Type": "application/pdf",
                    "Content-Disposition": 'attachment; filename="special-instruction.pdf"',
                }
                response.content = b"%PDF-special-instruction"
                return response
            if method == "POST" and url.endswith("/internal/special-instructions/DOC401/approve/"):
                return self._json_response(
                    {
                        "ok": True,
                        "ticket": {
                            "special_instruction": {
                                "current_status": "Document uploaded",
                                "status_code": "uploaded",
                            }
                        },
                    },
                    url=url,
                )
            raise AssertionError(f"Unexpected request {method} {url}")

        mock_request.side_effect = request_side_effect

        self.client.force_login(self.pm_user)
        download_response = self.client.get(
            reverse("ticketing:special_instruction_download", kwargs={"pk": review.ticket.pk})
        )
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response["Content-Type"], "application/pdf")
        self.assertEqual(download_response.content, b"%PDF-special-instruction")
        self.assertEqual(download_response["Content-Disposition"], 'attachment; filename="special-instruction.pdf"')

        approve_response = self.client.get(
            reverse("ticketing:special_instruction_approve", kwargs={"pk": review.ticket.pk}),
            follow=True,
        )
        self.assertEqual(approve_response.status_code, 200)
        review.refresh_from_db()
        review.ticket.refresh_from_db()
        self.assertIsNotNone(review.approved_at)
        self.assertEqual(review.approved_by, self.pm_user)
        self.assertEqual(review.rfa_current_status, "Document uploaded")
        self.assertEqual(review.ticket.status, Ticket.Status.COMPLETED)

        dashboard_response = self.client.get(reverse("dashboards:home"))
        self.assertContains(dashboard_response, "Doctor ID DOC401")
        self.assertContains(dashboard_response, "Document approval queue")
        self.assertContains(dashboard_response, "Approved")
