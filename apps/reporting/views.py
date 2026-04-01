from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.views.generic import TemplateView

from .contracts import REPORTING_API_CONTRACTS
from .services import get_subsystem_payload


class ReportingContractsView(LoginRequiredMixin, TemplateView):
    template_name = "reporting/contracts.jinja"
    template_engine = "jinja2"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["contracts"] = {
            **REPORTING_API_CONTRACTS,
            "red_flag_alert": {
                **REPORTING_API_CONTRACTS["red_flag_alert"],
                "endpoint": settings.REPORTING_API_RED_FLAG_ALERT_URL,
                "source": "live" if settings.REPORTING_API_USE_LIVE else "local placeholder",
            },
            "in_clinic": {
                **REPORTING_API_CONTRACTS["in_clinic"],
                "endpoint": settings.REPORTING_API_IN_CLINIC_URL,
                "source": "live" if settings.REPORTING_API_USE_LIVE else "local placeholder",
            },
            "patient_education": {
                **REPORTING_API_CONTRACTS["patient_education"],
                "endpoint": settings.REPORTING_API_PATIENT_EDUCATION_URL,
                "source": "live" if settings.REPORTING_API_USE_LIVE else "local placeholder",
            },
        }
        return context


def reporting_contracts_api(request):
    return JsonResponse(REPORTING_API_CONTRACTS)


def subsystem_feed(request, subsystem):
    try:
        payload = get_subsystem_payload(subsystem, request.GET.get("campaign"))
    except KeyError as exc:
        raise Http404("Unknown reporting subsystem.") from exc
    return JsonResponse(payload)
