from django.conf import settings


def normalize_email(value):
    return (value or "").strip().lower()


def email_has_project_manager_access(email):
    normalized_email = normalize_email(email)
    if not normalized_email:
        return False
    return normalized_email in getattr(settings, "PROJECT_MANAGER_EMAILS", ())


def sync_project_manager_access(user):
    if not email_has_project_manager_access(user.email):
        return []

    updated_fields = []
    if user.role != user.Role.PROJECT_MANAGER:
        user.role = user.Role.PROJECT_MANAGER
        updated_fields.append("role")
    if not user.is_staff:
        user.is_staff = True
        updated_fields.append("is_staff")
    return updated_fields
