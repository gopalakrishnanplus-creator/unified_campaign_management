import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView, View

from apps.campaigns.models import Campaign
from apps.ticketing.models import SpecialInstructionReview
from apps.ticketing.notifications import send_special_instruction_assignment_email
from apps.ticketing.special_instructions import (
    SpecialInstructionAPIError,
    create_or_update_special_instruction_review,
    fetch_special_instruction_ticket_payload,
)

from .services import (
    get_performance_dashboard_data,
    get_support_dashboard_data,
    get_system_status_dashboard_data,
)


class HomeView(TemplateView):
    template_name = "dashboards/home.jinja"
    template_engine = "jinja2"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["campaigns"] = Campaign.objects.order_by("name")
        return context


class ProjectManagerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser or self.request.user.is_project_manager


class ProjectManagementDashboardView(ProjectManagerRequiredMixin, TemplateView):
    template_name = "dashboards/project_management.jinja"
    template_engine = "jinja2"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["support_data"] = get_support_dashboard_data(
            special_instruction_page=self.request.GET.get("si_page") or 1,
            special_instruction_scope=self.request.GET.get("si_scope") or "active",
        )
        context["status_data"] = get_system_status_dashboard_data(self.request.build_absolute_uri("/").rstrip("/"))
        return context


class CampaignPerformanceDashboardView(ProjectManagerRequiredMixin, TemplateView):
    template_name = "dashboards/performance.jinja"
    template_engine = "jinja2"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["performance_data"] = get_performance_dashboard_data()
        return context


class SpecialInstructionFetchView(ProjectManagerRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        doctor_id = (request.POST.get("doctor_id") or "").strip()
        campaign_id = (request.POST.get("campaign_id") or "").strip()
        if not doctor_id:
            messages.error(request, "Doctor ID is required to fetch an RFA Special Instruction ticket.")
            return redirect("dashboards:home")
        try:
            payload = fetch_special_instruction_ticket_payload(
                doctor_id=doctor_id,
                campaign_id=campaign_id or None,
            )
            review = create_or_update_special_instruction_review(payload, actor=request.user)
        except SpecialInstructionAPIError as exc:
            messages.error(request, f"RFA Special Instruction ticket could not be fetched: {exc}")
            return redirect("dashboards:home")
        _send_special_instruction_assignment_email_if_needed(review, request.user, request)
        messages.success(
            request,
            f"Special Instruction review ticket {review.ticket.ticket_number} is assigned to {review.ticket.current_assignee.email}.",
        )
        return redirect("ticketing:detail", pk=review.ticket.pk)


class SpecialInstructionArchiveView(ProjectManagerRequiredMixin, View):
    def post(self, request, review_id, *args, **kwargs):
        review = get_object_or_404(SpecialInstructionReview.objects.select_related("ticket"), pk=review_id)
        action = (request.POST.get("action") or "archive").strip().lower()
        if action == "restore":
            review.archived_at = None
            review.archived_by = None
            review.save(update_fields=["archived_at", "archived_by", "updated_at"])
            messages.success(request, f"Special Instruction review {review.ticket.ticket_number} restored to the queue.")
        elif not review.archived_at:
            review.archived_at = timezone.now()
            review.archived_by = request.user
            review.save(update_fields=["archived_at", "archived_by", "updated_at"])
            messages.success(request, f"Special Instruction review {review.ticket.ticket_number} moved to archive.")
        else:
            messages.info(request, f"Special Instruction review {review.ticket.ticket_number} is already archived.")

        next_url = request.POST.get("next") or f"{reverse('dashboards:home')}#special-instruction-review"
        if not str(next_url).startswith("/"):
            next_url = f"{reverse('dashboards:home')}#special-instruction-review"
        return redirect(next_url)


def _special_instruction_request_token(request):
    authorization = (request.headers.get("Authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return (request.headers.get("X-Special-Instruction-Token") or "").strip()


def _send_special_instruction_assignment_email_if_needed(review, actor, request):
    if getattr(review, "assignment_notification_required", False):
        send_special_instruction_assignment_email(review.ticket, actor, request)


def _json_object(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _parse_special_instruction_body(request):
    content_type = (request.content_type or "").split(";", 1)[0].strip().lower()
    raw_body = (request.body or b"").strip()
    if content_type == "application/json" or raw_body.startswith(b"{"):
        try:
            parsed = json.loads(raw_body.decode("utf-8") or "{}")
        except ValueError as exc:
            raise ValueError("Invalid JSON payload.") from exc
        if not isinstance(parsed, dict):
            raise ValueError("JSON payload must be an object.")
        return parsed
    if request.POST:
        return request.POST.dict()
    return {}


def _looks_like_special_instruction_ticket(value):
    return isinstance(value.get("doctor"), dict) and (
        isinstance(value.get("special_instruction"), dict)
        or isinstance(value.get("associated_campaign"), dict)
        or isinstance(value.get("clinic"), dict)
    )


def _extract_special_instruction_payload(body, *, depth=0):
    if depth > 3:
        return {}
    candidate = _json_object(body)
    if not candidate:
        return {}
    if isinstance(candidate.get("ticket"), dict):
        return candidate
    if _looks_like_special_instruction_ticket(candidate):
        return {"ok": candidate.get("ok", True), "ticket": candidate}
    for key in ("payload", "data", "request", "ticket_payload", "ticketPayload", "body"):
        nested_payload = _extract_special_instruction_payload(candidate.get(key), depth=depth + 1)
        if nested_payload:
            return nested_payload
    return {}


def _extract_special_instruction_identifiers(body, *, depth=0):
    if depth > 3:
        return "", ""
    candidate = _json_object(body)
    if not candidate:
        return "", ""

    ticket = _json_object(candidate.get("ticket"))
    doctor = _json_object(candidate.get("doctor")) or _json_object(ticket.get("doctor"))
    campaign = (
        _json_object(candidate.get("associated_campaign"))
        or _json_object(candidate.get("campaign"))
        or _json_object(ticket.get("associated_campaign"))
        or _json_object(ticket.get("campaign"))
    )
    doctor_id = (
        candidate.get("doctor_id")
        or candidate.get("doctorId")
        or doctor.get("id")
        or ticket.get("doctor_id")
        or ticket.get("doctorId")
        or ""
    )
    campaign_id = (
        candidate.get("campaign_id")
        or candidate.get("campaignId")
        or campaign.get("campaign_id")
        or campaign.get("campaignId")
        or campaign.get("id")
        or ticket.get("campaign_id")
        or ticket.get("campaignId")
        or ""
    )
    if doctor_id:
        return str(doctor_id).strip(), str(campaign_id or "").strip()

    for key in ("payload", "data", "request", "ticket_payload", "ticketPayload", "body"):
        nested_doctor_id, nested_campaign_id = _extract_special_instruction_identifiers(
            candidate.get(key),
            depth=depth + 1,
        )
        if nested_doctor_id:
            return nested_doctor_id, nested_campaign_id
    return "", ""


@method_decorator(csrf_exempt, name="dispatch")
class SpecialInstructionWebhookView(View):
    def post(self, request, *args, **kwargs):
        expected_token = settings.SPECIAL_INSTRUCTION_PM_API_TOKEN
        provided_token = _special_instruction_request_token(request)
        if not expected_token or not provided_token or not constant_time_compare(provided_token, expected_token):
            return JsonResponse({"success": False, "error": "Unauthorized."}, status=403)

        try:
            body = _parse_special_instruction_body(request)
        except ValueError as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=400)

        try:
            payload = _extract_special_instruction_payload(body)
            if not payload:
                doctor_id, campaign_id = _extract_special_instruction_identifiers(body)
                if not doctor_id:
                    return JsonResponse({"success": False, "error": "doctor_id is required."}, status=400)
                payload = fetch_special_instruction_ticket_payload(
                    doctor_id=doctor_id,
                    campaign_id=campaign_id or None,
                )
            review = create_or_update_special_instruction_review(payload)
        except SpecialInstructionAPIError as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=502)
        _send_special_instruction_assignment_email_if_needed(review, review.ticket.created_by, request)

        return JsonResponse(
            {
                "success": True,
                "review_id": review.pk,
                "ticket_number": review.ticket.ticket_number,
                "ticket_url": request.build_absolute_uri(reverse("ticketing:detail", kwargs={"pk": review.ticket.pk})),
                "doctor_id": review.doctor_id,
                "status": review.rfa_status_code,
                "assignee_email": review.ticket.current_assignee.email,
            }
        )


class MyWorkRedirectView(LoginRequiredMixin, TemplateView):
    template_name = "dashboards/redirect.jinja"
    template_engine = "jinja2"

    def get(self, request, *args, **kwargs):
        if request.user.is_project_manager or request.user.is_superuser:
            return redirect("dashboards:home")
        return redirect("ticketing:list")
