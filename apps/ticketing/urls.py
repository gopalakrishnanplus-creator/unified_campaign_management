from django.urls import path

from .views import TicketCreateView, TicketDetailView, TicketListView


app_name = "ticketing"

urlpatterns = [
    path("", TicketListView.as_view(), name="list"),
    path("new/", TicketCreateView.as_view(), name="create"),
    path("<int:pk>/", TicketDetailView.as_view(), name="detail"),
]
