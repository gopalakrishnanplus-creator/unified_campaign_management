from django.urls import path

from .views import CampaignPerformanceDashboardView, MyWorkRedirectView, ProjectManagementDashboardView


app_name = "dashboards"

urlpatterns = [
    path("", ProjectManagementDashboardView.as_view(), name="home"),
    path("performance/", CampaignPerformanceDashboardView.as_view(), name="performance"),
    path("my-work/", MyWorkRedirectView.as_view(), name="my_work"),
]
