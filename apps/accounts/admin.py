from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "role", "department", "is_staff", "is_active")
    list_filter = ("role", "department", "is_staff", "is_active")
    search_fields = ("email", "full_name", "company")
    readonly_fields = ("last_login", "date_joined", "last_seen_at")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Profile"), {"fields": ("full_name", "role", "department", "title", "company", "phone_number", "timezone")}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined", "last_seen_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "role", "department", "password1", "password2", "is_staff", "is_active"),
            },
        ),
    )
