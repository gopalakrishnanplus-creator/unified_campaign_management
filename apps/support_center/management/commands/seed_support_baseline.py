from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.support_center.models import SupportCategory, SupportItem, SupportPage, SupportSuperCategory
from apps.ticketing.models import Department


class Command(BaseCommand):
    help = "Seeds the baseline support FAQ items required for customer-support and campaign-performance widget links."

    @transaction.atomic
    def handle(self, *args, **options):
        departments = self.ensure_departments()

        access_super, _ = SupportSuperCategory.objects.get_or_create(
            slug="access-login",
            defaults={"name": "Access & Login", "display_order": 1},
        )
        campaign_super, _ = SupportSuperCategory.objects.get_or_create(
            slug="campaign-operations",
            defaults={"name": "Campaign Operations", "display_order": 2},
        )
        reporting_super, _ = SupportSuperCategory.objects.get_or_create(
            slug="reporting-analytics",
            defaults={"name": "Reporting & Analytics", "display_order": 3},
        )

        auth_category, _ = SupportCategory.objects.get_or_create(
            super_category=access_super,
            slug="authentication",
            defaults={"name": "Authentication", "display_order": 1},
        )
        sharing_category, _ = SupportCategory.objects.get_or_create(
            super_category=campaign_super,
            slug="sharing-activation",
            defaults={"name": "Sharing & Activation", "display_order": 1},
        )
        reporting_category, _ = SupportCategory.objects.get_or_create(
            super_category=reporting_super,
            slug="reports-insights",
            defaults={"name": "Reports & Insights", "display_order": 1},
        )
        auth_page, _ = SupportPage.objects.get_or_create(
            slug="customer-support-authentication-page",
            defaults={"name": "Authentication Page", "source_system": "Customer support", "source_flow": "", "display_order": 1},
        )
        sharing_page, _ = SupportPage.objects.get_or_create(
            slug="customer-support-sharing-activation-page",
            defaults={"name": "Sharing & Activation Page", "source_system": "Customer support", "source_flow": "", "display_order": 2},
        )
        reporting_page, _ = SupportPage.objects.get_or_create(
            slug="campaign-performance-reports-insights-page",
            defaults={"name": "Reports & Insights Page", "source_system": "Campaign performance", "source_flow": "", "display_order": 3},
        )

        SupportItem.objects.update_or_create(
            category=auth_category,
            slug="google-sign-in-not-working",
            defaults={
                "page": auth_page,
                "name": "Google sign-in is not working",
                "summary": "Troubleshoot browser session, allowed domain, and pop-up restrictions.",
                "knowledge_type": SupportItem.KnowledgeType.FAQ,
                "response_mode": SupportItem.ResponseMode.STANDARDIZED,
                "solution_title": "Reset the browser session and confirm the allowed Google account",
                "solution_body": "Ask the user to clear the previous Google session, re-open the login screen, allow browser pop-ups, and retry with the approved work email.",
                "associated_pdf_url": "https://example.com/google-auth-checklist.pdf",
                "ticket_department": departments["technical"],
                "default_ticket_type": "Authentication issue",
                "source_system": "Customer support",
                "source_flow": "",
                "ticket_required": False,
                "display_order": 1,
                "is_active": True,
                "is_visible_to_doctors": False,
                "is_visible_to_clinic_staff": False,
                "is_visible_to_brand_managers": True,
                "is_visible_to_field_reps": True,
                "is_visible_to_patients": False,
            },
        )

        SupportItem.objects.update_or_create(
            category=sharing_category,
            slug="doctor-not-added-to-campaign",
            defaults={
                "page": sharing_page,
                "name": "Doctor or clinic has not been added to the campaign",
                "summary": "Escalate onboarding gaps to campaign operations.",
                "knowledge_type": SupportItem.KnowledgeType.FAQ,
                "response_mode": SupportItem.ResponseMode.DIRECT_TICKET,
                "solution_title": "Raise a campaign operations ticket",
                "solution_body": "If the doctor or clinic is missing from the campaign setup, capture the onboarding context and escalate to campaign operations.",
                "ticket_department": departments["campaign_ops"],
                "default_ticket_type": "Campaign onboarding issue",
                "source_system": "Customer support",
                "source_flow": "",
                "ticket_required": True,
                "display_order": 2,
                "is_active": True,
                "is_visible_to_doctors": True,
                "is_visible_to_clinic_staff": True,
                "is_visible_to_brand_managers": True,
                "is_visible_to_field_reps": True,
                "is_visible_to_patients": False,
            },
        )

        SupportItem.objects.update_or_create(
            category=reporting_category,
            slug="weekly-report-missing",
            defaults={
                "page": reporting_page,
                "name": "Weekly campaign report is missing",
                "summary": "Escalate missing or delayed reporting data to analytics.",
                "knowledge_type": SupportItem.KnowledgeType.FAQ,
                "response_mode": SupportItem.ResponseMode.DIRECT_TICKET,
                "solution_title": "Raise a reporting escalation",
                "solution_body": "Capture the campaign, expected report window, and affected geography, then escalate the issue to campaign analytics.",
                "ticket_department": departments["analytics"],
                "default_ticket_type": "Reporting issue",
                "source_system": "Campaign performance",
                "source_flow": "",
                "ticket_required": True,
                "display_order": 3,
                "is_active": True,
                "is_visible_to_doctors": True,
                "is_visible_to_clinic_staff": True,
                "is_visible_to_brand_managers": True,
                "is_visible_to_field_reps": True,
                "is_visible_to_patients": False,
            },
        )

        self.stdout.write(self.style.SUCCESS("Seeded baseline support FAQ catalog."))

    def ensure_departments(self):
        definitions = {
            "campaign_ops": {
                "user_email": "ops@inditech.co.in",
                "user_name": "Clinical Operations Lead",
                "user_role": User.Role.DEPARTMENT_OWNER,
                "department_code": "CAMP-OPS",
                "department_name": "Campaign Operations",
                "department_email": "campaign-ops@inditech.co.in",
            },
            "analytics": {
                "user_email": "analytics@inditech.co.in",
                "user_name": "Analytics Lead",
                "user_role": User.Role.DEPARTMENT_OWNER,
                "department_code": "ANALYTICS",
                "department_name": "Campaign Analytics",
                "department_email": "analytics-support@inditech.co.in",
            },
            "technical": {
                "user_email": "support.tech@inditech.co.in",
                "user_name": "Technical Support Lead",
                "user_role": User.Role.DEPARTMENT_OWNER,
                "department_code": "TECH",
                "department_name": "Technical Support",
                "department_email": "tech-support@inditech.co.in",
            },
        }

        departments = {}
        for config in definitions.values():
            user, _ = User.objects.update_or_create(
                email=config["user_email"],
                defaults={
                    "full_name": config["user_name"],
                    "role": config["user_role"],
                    "is_staff": True,
                    "company": "Inditech",
                },
            )
            department, _ = Department.objects.update_or_create(
                code=config["department_code"],
                defaults={
                    "name": config["department_name"],
                    "support_email": config["department_email"],
                    "default_recipient": user,
                    "is_active": True,
                },
            )
            if user.department_id != department.id:
                user.department = department
                user.save(update_fields=["department"])
            departments[config["department_code"]] = department

        pm_user, _ = User.objects.update_or_create(
            email=settings.PROJECT_MANAGER_EMAIL,
            defaults={
                "full_name": "Campaign Project Manager",
                "role": User.Role.PROJECT_MANAGER,
                "is_staff": True,
                "company": "Inditech",
            },
        )
        if not pm_user.is_staff:
            pm_user.is_staff = True
            pm_user.save(update_fields=["is_staff"])

        return {
            "campaign_ops": departments["CAMP-OPS"],
            "analytics": departments["ANALYTICS"],
            "technical": departments["TECH"],
        }
