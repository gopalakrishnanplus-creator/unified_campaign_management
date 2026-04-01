from django.urls import path

from .views import CampaignDetailView, CampaignListView


app_name = "campaigns"

urlpatterns = [
    path("", CampaignListView.as_view(), name="list"),
    path("<slug:slug>/", CampaignDetailView.as_view(), name="detail"),
]
