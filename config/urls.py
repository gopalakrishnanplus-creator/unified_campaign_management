from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.dashboards.views import HomeView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", HomeView.as_view(), name="home"),
    path("accounts/", include("apps.accounts.urls")),
    path("accounts/", include("allauth.urls")),
    path("app/", include("apps.dashboards.urls")),
    path("support/", include("apps.support_center.urls")),
    path("ticketing/", include("apps.ticketing.urls")),
    path("campaigns/", include("apps.campaigns.urls")),
    path("reporting/", include("apps.reporting.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
