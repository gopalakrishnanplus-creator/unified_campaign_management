from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.campaigns.models import Campaign

from .services import get_performance_dashboard_data, get_selected_campaign, get_support_dashboard_data


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
        selected_campaign = get_selected_campaign(self.request.GET.get("campaign"))
        context["campaigns"] = Campaign.objects.order_by("name")
        context["selected_campaign"] = selected_campaign
        context["support_data"] = get_support_dashboard_data(selected_campaign)
        context["performance_data"] = get_performance_dashboard_data(selected_campaign)
        return context


class MyWorkRedirectView(LoginRequiredMixin, TemplateView):
    template_name = "dashboards/redirect.jinja"
    template_engine = "jinja2"

    def get(self, request, *args, **kwargs):
        if request.user.is_project_manager or request.user.is_superuser:
            return redirect("dashboards:home")
        return redirect("ticketing:list")
