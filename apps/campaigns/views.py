from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView, ListView

from .models import Campaign


class CampaignListView(LoginRequiredMixin, ListView):
    template_name = "campaigns/list.jinja"
    template_engine = "jinja2"
    model = Campaign
    context_object_name = "campaigns"

    def get_queryset(self):
        return (
            Campaign.objects.annotate(
                enrolled_clinics=Count("clinic_enrollments__clinic", distinct=True),
                assigned_field_reps=Count("field_rep_assignments", distinct=True),
            )
            .order_by("name")
        )


class CampaignDetailView(LoginRequiredMixin, DetailView):
    template_name = "campaigns/detail.jinja"
    template_engine = "jinja2"
    model = Campaign
    context_object_name = "campaign"
    slug_field = "slug"

    def get_object(self, queryset=None):
        return get_object_or_404(
            Campaign.objects.prefetch_related("field_rep_assignments__field_rep", "clinic_enrollments__clinic"),
            slug=self.kwargs["slug"],
        )
