from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.access import sync_project_manager_access
from apps.accounts.models import User


@override_settings(
    PROJECT_MANAGER_EMAIL="campaignpm@inditech.co.in",
    PROJECT_MANAGER_EMAILS=("campaignpm@inditech.co.in", "pm.two@inditech.co.in", "pm.three@inditech.co.in"),
)
class ProjectManagerAllowlistTests(TestCase):
    def test_allowlisted_secondary_pm_email_can_access_dashboard(self):
        user = User.objects.create_user(
            email="pm.two@inditech.co.in",
            password="unused-password",
            full_name="Second PM",
            role=User.Role.SUPPORT_AGENT,
        )

        self.client.force_login(user)
        response = self.client.get(reverse("dashboards:home"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(user.is_project_manager)

    def test_non_allowlisted_email_cannot_access_dashboard(self):
        user = User.objects.create_user(
            email="regular.user@inditech.co.in",
            password="unused-password",
            full_name="Regular User",
            role=User.Role.SUPPORT_AGENT,
        )

        self.client.force_login(user)
        response = self.client.get(reverse("dashboards:home"))

        self.assertEqual(response.status_code, 403)
        self.assertFalse(user.is_project_manager)

    def test_sync_project_manager_access_promotes_allowlisted_user(self):
        user = User.objects.create_user(
            email="pm.three@inditech.co.in",
            password="unused-password",
            full_name="Third PM",
            role=User.Role.SUPPORT_AGENT,
            is_staff=False,
        )

        updated_fields = sync_project_manager_access(user)

        self.assertEqual(set(updated_fields), {"role", "is_staff"})
        self.assertEqual(user.role, User.Role.PROJECT_MANAGER)
        self.assertTrue(user.is_staff)
