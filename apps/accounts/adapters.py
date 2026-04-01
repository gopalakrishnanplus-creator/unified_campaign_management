from django.conf import settings

from allauth.account.adapter import DefaultAccountAdapter


class AccountAdapter(DefaultAccountAdapter):
    def populate_username(self, request, user):
        return None

    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=False)
        user.full_name = form.cleaned_data.get("full_name") or user.email.split("@")[0]
        if user.email.lower() == settings.PROJECT_MANAGER_EMAIL.lower():
            user.role = user.Role.PROJECT_MANAGER
            user.is_staff = True
        if commit:
            user.save()
        return user
