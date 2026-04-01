from django.urls import path

from .views import MyWorkRedirectView, ProjectManagementDashboardView


app_name = "dashboards"

urlpatterns = [
    path("", ProjectManagementDashboardView.as_view(), name="home"),
    path("my-work/", MyWorkRedirectView.as_view(), name="my_work"),
]
