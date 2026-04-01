from django.conf import settings


def auth_configuration(request):
    google_apps = settings.SOCIALACCOUNT_PROVIDERS.get("google", {}).get("APPS", [])
    return {
        "google_oauth_enabled": bool(google_apps),
    }
