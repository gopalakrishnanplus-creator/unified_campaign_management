from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.campaigns.models import Campaign

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


class MyWorkRedirectView(LoginRequiredMixin, TemplateView):
    template_name = "dashboards/redirect.jinja"
    template_engine = "jinja2"

    def get(self, request, *args, **kwargs):
        if request.user.is_project_manager or request.user.is_superuser:
            return redirect("dashboards:home")
        return redirect("ticketing:list")
