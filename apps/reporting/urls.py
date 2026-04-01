from django.urls import path

from .views import ReportingContractsView, reporting_contracts_api, subsystem_feed


app_name = "reporting"

urlpatterns = [
    path("contracts/", ReportingContractsView.as_view(), name="contracts"),
    path("api/contracts/", reporting_contracts_api, name="contracts_api"),
    path("api/<slug:subsystem>/", subsystem_feed, name="subsystem_feed"),
]
