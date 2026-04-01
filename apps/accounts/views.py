from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View

from .models import User


class DevelopmentLoginView(View):
    def get(self, request, *args, **kwargs):
        if not settings.ENABLE_DEV_LOGIN:
            messages.error(request, "Development login is disabled.")
            return redirect("account_login")

        user, _ = User.objects.get_or_create(
            email=settings.PROJECT_MANAGER_EMAIL,
            defaults={
                "full_name": "Campaign Project Manager",
                "role": User.Role.PROJECT_MANAGER,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        user.backend = "django.contrib.auth.backends.ModelBackend"
        login(request, user)
        messages.success(request, f"Signed in locally as {user.email}.")
        return redirect("dashboards:home")


class AccountHealthView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        request.user.last_seen_at = request.user.last_login
        request.user.save(update_fields=["last_seen_at"])
        return redirect("dashboards:home")
