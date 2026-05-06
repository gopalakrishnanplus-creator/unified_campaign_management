import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView, View

from apps.campaigns.models import Campaign
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
        context["support_data"] = get_support_dashboard_data()
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
        messages.success(
            request,
            f"Special Instruction review ticket {review.ticket.ticket_number} is ready for assignment.",
        )
        return redirect("ticketing:detail", pk=review.ticket.pk)


def _special_instruction_request_token(request):
    authorization = (request.headers.get("Authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return (request.headers.get("X-Special-Instruction-Token") or "").strip()


@method_decorator(csrf_exempt, name="dispatch")
class SpecialInstructionWebhookView(View):
    def post(self, request, *args, **kwargs):
        expected_token = settings.SPECIAL_INSTRUCTION_PM_API_TOKEN
        provided_token = _special_instruction_request_token(request)
        if not expected_token or not provided_token or not constant_time_compare(provided_token, expected_token):
            return JsonResponse({"success": False, "error": "Unauthorized."}, status=403)

        try:
            body = json.loads((request.body or b"{}").decode("utf-8") or "{}")
        except ValueError:
            return JsonResponse({"success": False, "error": "Invalid JSON payload."}, status=400)

        try:
            if body.get("ticket"):
                payload = body
            else:
                doctor_id = (body.get("doctor_id") or body.get("doctorId") or "").strip()
                campaign_id = (body.get("campaign_id") or body.get("campaignId") or "").strip()
                if not doctor_id:
                    return JsonResponse({"success": False, "error": "doctor_id is required."}, status=400)
                payload = fetch_special_instruction_ticket_payload(
                    doctor_id=doctor_id,
                    campaign_id=campaign_id or None,
                )
            review = create_or_update_special_instruction_review(payload)
        except SpecialInstructionAPIError as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=502)

        return JsonResponse(
            {
                "success": True,
                "review_id": review.pk,
                "ticket_number": review.ticket.ticket_number,
                "ticket_url": request.build_absolute_uri(reverse("ticketing:detail", kwargs={"pk": review.ticket.pk})),
                "doctor_id": review.doctor_id,
                "status": review.rfa_status_code,
            }
        )


class MyWorkRedirectView(LoginRequiredMixin, TemplateView):
    template_name = "dashboards/redirect.jinja"
    template_engine = "jinja2"

    def get(self, request, *args, **kwargs):
        if request.user.is_project_manager or request.user.is_superuser:
            return redirect("dashboards:home")
        return redirect("ticketing:list")
