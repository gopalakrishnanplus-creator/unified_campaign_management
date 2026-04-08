from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.campaigns.models import Campaign
from apps.ticketing.models import Department, TicketCategory, TicketTypeDefinition
from apps.ticketing.services import seed_default_ticket_taxonomy


DEPARTMENT_SEED = [
    {
        "user_email": "ops@inditech.co.in",
        "user_name": "Clinical Operations Lead",
        "user_role": User.Role.DEPARTMENT_OWNER,
        "department_code": "CAMP-OPS",
        "department_name": "Campaign Operations",
        "department_description": "Handles clinic onboarding, campaign activation, and field rep support.",
        "support_email": "campaign-ops@inditech.co.in",
    },
    {
        "user_email": "analytics@inditech.co.in",
        "user_name": "Analytics Lead",
        "user_role": User.Role.DEPARTMENT_OWNER,
        "department_code": "ANALYTICS",
        "department_name": "Campaign Analytics",
        "department_description": "Handles reporting, KPI analysis, and performance questions.",
        "support_email": "analytics-support@inditech.co.in",
    },
    {
        "user_email": "support.tech@inditech.co.in",
        "user_name": "Technical Support Lead",
        "user_role": User.Role.DEPARTMENT_OWNER,
        "department_code": "TECH",
        "department_name": "Technical Support",
        "department_description": "Handles access, login, and troubleshooting issues.",
        "support_email": "tech-support@inditech.co.in",
    },
]

CAMPAIGN_SEED = [
    {
        "name": "General Support Campaign",
        "brand_name": "Inditech",
        "description": "Fallback campaign for ticket logging when a specific campaign has not been configured yet.",
        "status": Campaign.Status.ACTIVE,
        "geography": "India",
        "start_offset_days": -30,
        "end_offset_days": 365,
        "has_in_clinic": True,
        "has_red_flag_alerts": True,
        "has_patient_education": True,
    },
    {
        "name": "CardioPlus Unified Care",
        "brand_name": "CardioPlus",
        "description": "Integrated campaign spanning in-clinic sharing, red flag alerts, and patient education.",
        "status": Campaign.Status.ACTIVE,
        "geography": "South India",
        "start_offset_days": -45,
        "end_offset_days": 90,
        "has_in_clinic": True,
        "has_red_flag_alerts": True,
        "has_patient_education": True,
    },
    {
        "name": "GlucoCare Education Drive",
        "brand_name": "GlucoCare",
        "description": "Patient education and clinic adoption campaign for diabetes care.",
        "status": Campaign.Status.ACTIVE,
        "geography": "West India",
        "start_offset_days": -20,
        "end_offset_days": 120,
        "has_in_clinic": True,
        "has_red_flag_alerts": True,
        "has_patient_education": True,
    },
]


class Command(BaseCommand):
    help = "Seeds the baseline ticket categories, ticket types, departments, and campaigns required for the ticket-create form dropdowns."

    @transaction.atomic
    def handle(self, *args, **options):
        pm_user, _ = User.objects.update_or_create(
            email=settings.PROJECT_MANAGER_EMAIL,
            defaults={
                "full_name": "Campaign Project Manager",
                "role": User.Role.PROJECT_MANAGER,
                "is_staff": True,
                "company": "Inditech",
                "title": "Project Manager",
            },
        )
        if not pm_user.is_staff:
            pm_user.is_staff = True
            pm_user.save(update_fields=["is_staff"])

        created_departments = self.seed_departments()
        seed_default_ticket_taxonomy()
        created_campaigns = self.seed_campaigns()

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded ticketing dropdown data: "
                f"{Department.objects.count()} departments, "
                f"{TicketCategory.objects.count()} ticket categories, "
                f"{TicketTypeDefinition.objects.count()} ticket types, "
                f"{Campaign.objects.count()} campaigns."
            )
        )
        if created_departments or created_campaigns:
            self.stdout.write(
                f"Updated/created departments: {created_departments}; campaigns: {created_campaigns}"
            )

    def seed_departments(self):
        touched = []
        for config in DEPARTMENT_SEED:
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
                    "description": config["department_description"],
                    "support_email": config["support_email"],
                    "default_recipient": user,
                    "is_active": True,
                },
            )
            if user.department_id != department.id:
                user.department = department
                user.save(update_fields=["department"])
            touched.append(department.code)
        return touched

    def seed_campaigns(self):
        today = date.today()
        touched = []
        for config in CAMPAIGN_SEED:
            campaign, _ = Campaign.objects.update_or_create(
                name=config["name"],
                defaults={
                    "brand_name": config["brand_name"],
                    "description": config["description"],
                    "status": config["status"],
                    "geography": config["geography"],
                    "start_date": today + timedelta(days=config["start_offset_days"]),
                    "end_date": today + timedelta(days=config["end_offset_days"]),
                    "has_in_clinic": config["has_in_clinic"],
                    "has_red_flag_alerts": config["has_red_flag_alerts"],
                    "has_patient_education": config["has_patient_education"],
                    "support_contact_email": settings.PROJECT_MANAGER_EMAIL,
                },
            )
            touched.append(campaign.slug)
        return touched
