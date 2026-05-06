from django.urls import path

from .views import (
    SpecialInstructionApproveView,
    SpecialInstructionDownloadView,
    TicketCreateView,
    TicketDetailView,
    TicketDistributionView,
    TicketEscalateView,
    TicketListView,
)


app_name = "ticketing"

urlpatterns = [
    path("", TicketListView.as_view(), name="list"),
    path("distribution/", TicketDistributionView.as_view(), name="distribution"),
    path("new/", TicketCreateView.as_view(), name="create"),
    path("<int:pk>/escalate/", TicketEscalateView.as_view(), name="escalate"),
    path("<int:pk>/special-instruction/download/", SpecialInstructionDownloadView.as_view(), name="special_instruction_download"),
    path("<int:pk>/special-instruction/approve/", SpecialInstructionApproveView.as_view(), name="special_instruction_approve"),
    path("<int:pk>/", TicketDetailView.as_view(), name="detail"),
]
