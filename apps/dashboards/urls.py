from django.urls import path

from .views import (
    CampaignPerformanceDashboardView,
    MyWorkRedirectView,
    ProjectManagementDashboardView,
    SpecialInstructionArchiveView,
    SpecialInstructionFetchView,
    SpecialInstructionWebhookView,
)


app_name = "dashboards"

urlpatterns = [
    path("", ProjectManagementDashboardView.as_view(), name="home"),
    path("performance/", CampaignPerformanceDashboardView.as_view(), name="performance"),
    path("special-instructions/<int:review_id>/archive/", SpecialInstructionArchiveView.as_view(), name="special_instruction_archive"),
    path("special-instructions/fetch/", SpecialInstructionFetchView.as_view(), name="special_instruction_fetch"),
    path("special-instructions/webhook", SpecialInstructionWebhookView.as_view(), name="special_instruction_webhook_no_slash"),
    path("special-instructions/webhook/", SpecialInstructionWebhookView.as_view(), name="special_instruction_webhook"),
    path("my-work/", MyWorkRedirectView.as_view(), name="my_work"),
]
