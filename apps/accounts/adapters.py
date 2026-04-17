from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from .access import sync_project_manager_access


class AccountAdapter(DefaultAccountAdapter):
    def populate_username(self, request, user):
        return None

    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=False)
        user.full_name = form.cleaned_data.get("full_name") or user.email.split("@")[0]
        sync_project_manager_access(user)
        if commit:
            user.save()
        return user


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        super().pre_social_login(request, sociallogin)
        user = getattr(sociallogin, "user", None)
        if not user:
            return
        updated_fields = sync_project_manager_access(user)
        if user.pk and updated_fields:
            user.save(update_fields=updated_fields)

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form=form)
        updated_fields = sync_project_manager_access(user)
        if updated_fields:
            user.save(update_fields=updated_fields)
        return user
