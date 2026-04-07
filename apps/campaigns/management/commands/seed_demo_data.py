from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.campaigns.models import Campaign, CampaignClinicEnrollment, CampaignFieldRepAssignment, Clinic, ClinicGroup, Doctor
from apps.reporting.models import AdoptionSnapshot, ExternalGrowthSnapshot, InClinicSnapshot, PatientEducationSnapshot, RedFlagSnapshot
from apps.support_center.models import SupportCategory, SupportItem, SupportRequest, SupportSuperCategory
from apps.ticketing.models import Department, Ticket, TicketNote
from apps.ticketing.services import change_ticket_status, create_ticket, resolve_ticket_classification, seed_default_ticket_taxonomy


class Command(BaseCommand):
    help = "Seeds the local development database with campaigns, support catalog entries, tickets, and reporting snapshots."

    @transaction.atomic
    def handle(self, *args, **options):
        today = date.today()
        seed_default_ticket_taxonomy()

        pm_user, _ = User.objects.update_or_create(
            email=settings.PROJECT_MANAGER_EMAIL,
            defaults={
                "full_name": "Campaign Project Manager",
                "role": User.Role.PROJECT_MANAGER,
                "is_staff": True,
                "is_superuser": True,
                "company": "Inditech",
                "title": "Project Manager",
            },
        )

        operations_user, _ = User.objects.update_or_create(
            email="ops@inditech.co.in",
            defaults={
                "full_name": "Clinical Operations Lead",
                "role": User.Role.DEPARTMENT_OWNER,
                "is_staff": True,
                "company": "Inditech",
                "title": "Operations Lead",
            },
        )
        analytics_user, _ = User.objects.update_or_create(
            email="analytics@inditech.co.in",
            defaults={
                "full_name": "Analytics Lead",
                "role": User.Role.DEPARTMENT_OWNER,
                "is_staff": True,
                "company": "Inditech",
                "title": "Analytics Lead",
            },
        )
        tech_user, _ = User.objects.update_or_create(
            email="support.tech@inditech.co.in",
            defaults={
                "full_name": "Technical Support Lead",
                "role": User.Role.DEPARTMENT_OWNER,
                "is_staff": True,
                "company": "Inditech",
                "title": "Technical Support Lead",
            },
        )
        field_rep_user, _ = User.objects.update_or_create(
            email="meera.rep@example.com",
            defaults={
                "full_name": "Meera Kapoor",
                "role": User.Role.FIELD_REP,
                "company": "CardioPlus",
                "title": "Field Representative",
            },
        )
        field_rep_user_2, _ = User.objects.update_or_create(
            email="rajan.rep@example.com",
            defaults={
                "full_name": "Rajan Menon",
                "role": User.Role.FIELD_REP,
                "company": "GlucoCare",
                "title": "Field Representative",
            },
        )
        brand_manager_user, _ = User.objects.update_or_create(
            email="brand.manager@example.com",
            defaults={
                "full_name": "Priya Shah",
                "role": User.Role.BRAND_MANAGER,
                "company": "CardioPlus",
                "title": "Brand Manager",
            },
        )

        campaign_ops, _ = Department.objects.update_or_create(
            code="CAMP-OPS",
            defaults={
                "name": "Campaign Operations",
                "description": "Handles clinic onboarding, campaign activation, and field rep support.",
                "support_email": "campaign-ops@inditech.co.in",
                "default_recipient": operations_user,
            },
        )
        analytics, _ = Department.objects.update_or_create(
            code="ANALYTICS",
            defaults={
                "name": "Campaign Analytics",
                "description": "Handles reporting, KPI analysis, and performance questions.",
                "support_email": "analytics-support@inditech.co.in",
                "default_recipient": analytics_user,
            },
        )
        technical, _ = Department.objects.update_or_create(
            code="TECH",
            defaults={
                "name": "Technical Support",
                "description": "Handles access, login, and troubleshooting issues.",
                "support_email": "tech-support@inditech.co.in",
                "default_recipient": tech_user,
            },
        )

        for user, department in [(operations_user, campaign_ops), (analytics_user, analytics), (tech_user, technical)]:
            user.department = department
            user.save(update_fields=["department"])

        cardio_campaign, _ = Campaign.objects.update_or_create(
            slug="cardioplus-unified-care",
            defaults={
                "name": "CardioPlus Unified Care",
                "brand_name": "CardioPlus",
                "description": "An integrated campaign spanning in-clinic sharing, red flag alerts, and patient education.",
                "status": Campaign.Status.ACTIVE,
                "geography": "South India",
                "start_date": today - timedelta(days=45),
                "end_date": today + timedelta(days=90),
                "has_in_clinic": True,
                "has_red_flag_alerts": True,
                "has_patient_education": True,
                "support_contact_email": settings.PROJECT_MANAGER_EMAIL,
            },
        )
        gluco_campaign, _ = Campaign.objects.update_or_create(
            slug="glucocare-education-drive",
            defaults={
                "name": "GlucoCare Education Drive",
                "brand_name": "GlucoCare",
                "description": "Patient education and clinic adoption campaign for diabetes care.",
                "status": Campaign.Status.ACTIVE,
                "geography": "West India",
                "start_date": today - timedelta(days=20),
                "end_date": today + timedelta(days=120),
                "has_in_clinic": True,
                "has_red_flag_alerts": True,
                "has_patient_education": True,
                "support_contact_email": settings.PROJECT_MANAGER_EMAIL,
            },
        )

        bengaluru_group, _ = ClinicGroup.objects.get_or_create(name="Bengaluru Metro", geography="Karnataka")
        mumbai_group, _ = ClinicGroup.objects.get_or_create(name="Mumbai Central", geography="Maharashtra")

        clinic_a, _ = Clinic.objects.update_or_create(
            clinic_code="BLR-001",
            defaults={"name": "Green Heart Clinic", "clinic_group": bengaluru_group, "city": "Bengaluru", "state": "Karnataka"},
        )
        clinic_b, _ = Clinic.objects.update_or_create(
            clinic_code="BOM-010",
            defaults={"name": "Harbor Diabetes Centre", "clinic_group": mumbai_group, "city": "Mumbai", "state": "Maharashtra"},
        )

        doctor_a, _ = Doctor.objects.update_or_create(
            email="doctor.iyer@example.com",
            defaults={
                "full_name": "Dr. Ananya Iyer",
                "clinic": clinic_a,
                "specialty": "Cardiology",
                "is_onboarded": True,
                "is_growth_clinic_member": True,
            },
        )
        doctor_b, _ = Doctor.objects.update_or_create(
            email="doctor.singh@example.com",
            defaults={
                "full_name": "Dr. Karan Singh",
                "clinic": clinic_b,
                "specialty": "Diabetology",
                "is_onboarded": True,
                "is_growth_clinic_member": False,
            },
        )

        CampaignFieldRepAssignment.objects.update_or_create(
            campaign=cardio_campaign,
            field_rep=field_rep_user,
            defaults={"territory": "Bengaluru", "assigned_at": today - timedelta(days=40), "is_active": True},
        )
        CampaignFieldRepAssignment.objects.update_or_create(
            campaign=gluco_campaign,
            field_rep=field_rep_user_2,
            defaults={"territory": "Mumbai", "assigned_at": today - timedelta(days=18), "is_active": True},
        )

        for campaign, clinic, doctor, rep, system_name, enrolled_on in [
            (cardio_campaign, clinic_a, doctor_a, field_rep_user, CampaignClinicEnrollment.SourceSystem.IN_CLINIC, today - timedelta(days=38)),
            (cardio_campaign, clinic_a, doctor_a, field_rep_user, CampaignClinicEnrollment.SourceSystem.RED_FLAG_ALERT, today - timedelta(days=30)),
            (cardio_campaign, clinic_a, doctor_a, field_rep_user, CampaignClinicEnrollment.SourceSystem.PATIENT_EDUCATION, today - timedelta(days=25)),
            (gluco_campaign, clinic_b, doctor_b, field_rep_user_2, CampaignClinicEnrollment.SourceSystem.PATIENT_EDUCATION, today - timedelta(days=15)),
            (gluco_campaign, clinic_b, doctor_b, field_rep_user_2, CampaignClinicEnrollment.SourceSystem.IN_CLINIC, today - timedelta(days=12)),
        ]:
            CampaignClinicEnrollment.objects.update_or_create(
                campaign=campaign,
                clinic=clinic,
                doctor=doctor,
                source_system=system_name,
                defaults={"field_rep": rep, "enrolled_on": enrolled_on},
            )

        access_super, _ = SupportSuperCategory.objects.get_or_create(name="Access & Login", defaults={"display_order": 1})
        campaign_super, _ = SupportSuperCategory.objects.get_or_create(name="Campaign Operations", defaults={"display_order": 2})
        reporting_super, _ = SupportSuperCategory.objects.get_or_create(name="Reporting & Analytics", defaults={"display_order": 3})

        auth_category, _ = SupportCategory.objects.get_or_create(super_category=access_super, slug="authentication", defaults={"name": "Authentication", "display_order": 1})
        sharing_category, _ = SupportCategory.objects.get_or_create(super_category=campaign_super, slug="sharing-activation", defaults={"name": "Sharing & Activation", "display_order": 1})
        reporting_category, _ = SupportCategory.objects.get_or_create(super_category=reporting_super, slug="reports-insights", defaults={"name": "Reports & Insights", "display_order": 1})

        SupportItem.objects.update_or_create(
            category=auth_category,
            slug="google-sign-in-not-working",
            defaults={
                "name": "Google sign-in is not working",
                "summary": "Troubleshoot browser session, allowed domain, and pop-up restrictions.",
                "response_mode": SupportItem.ResponseMode.STANDARDIZED,
                "solution_title": "Reset the browser session and confirm the allowed Google account",
                "solution_body": "Ask the user to clear the previous Google session, re-open the login screen, allow browser pop-ups, and retry with the approved work email.",
                "associated_pdf_url": "https://example.com/google-auth-checklist.pdf",
                "ticket_department": technical,
                "default_ticket_type": "Authentication issue",
                "source_system": "Customer support",
                "is_visible_to_brand_managers": True,
                "is_visible_to_field_reps": True,
                "is_visible_to_doctors": False,
                "is_visible_to_clinic_staff": False,
            },
        )
        SupportItem.objects.update_or_create(
            category=sharing_category,
            slug="doctor-not-added-to-campaign",
            defaults={
                "name": "Doctor or clinic has not been added to the campaign",
                "summary": "Escalate onboarding gaps to campaign operations.",
                "response_mode": SupportItem.ResponseMode.DIRECT_TICKET,
                "ticket_department": campaign_ops,
                "default_ticket_type": "Campaign onboarding issue",
                "source_system": "Customer support",
            },
        )
        SupportItem.objects.update_or_create(
            category=sharing_category,
            slug="in-clinic-collateral-not-opening",
            defaults={
                "name": "In-clinic collateral is not opening",
                "summary": "Provide the self-checklist for link opens, PDF access, and WhatsApp share formatting.",
                "response_mode": SupportItem.ResponseMode.STANDARDIZED,
                "solution_title": "Verify link format and clinic browser permissions",
                "solution_body": "Confirm the field rep used the current campaign link, the doctor opened the correct month collateral, and the clinic browser allows PDF/video content to load.",
                "associated_video_url": "https://example.com/in-clinic-help-video",
                "ticket_department": campaign_ops,
                "default_ticket_type": "In-clinic content issue",
                "source_system": "In-clinic",
            },
        )
        SupportItem.objects.update_or_create(
            category=reporting_category,
            slug="weekly-report-missing",
            defaults={
                "name": "Weekly campaign report is missing",
                "summary": "Escalate missing or delayed reporting data to analytics.",
                "response_mode": SupportItem.ResponseMode.DIRECT_TICKET,
                "ticket_department": analytics,
                "default_ticket_type": "Reporting issue",
                "source_system": "Campaign performance",
            },
        )

        request_1, _ = SupportRequest.objects.get_or_create(
            requester_email="doctor.iyer@example.com",
            subject="In-clinic collateral is not opening",
            defaults={
                "user_type": "doctor",
                "requester_name": "Dr. Ananya Iyer",
                "requester_company": "Green Heart Clinic",
                "campaign": cardio_campaign,
                "item": SupportItem.objects.get(slug="in-clinic-collateral-not-opening"),
                "free_text": "The PDF opens but the embedded video is not visible on mobile.",
                "status": SupportRequest.Status.TICKET_CREATED,
            },
        )
        request_2, _ = SupportRequest.objects.get_or_create(
            requester_email="brand.manager@example.com",
            subject="Weekly campaign report is missing",
            defaults={
                "user_type": "brand_manager",
                "requester_name": "Priya Shah",
                "requester_company": "CardioPlus",
                "campaign": cardio_campaign,
                "item": SupportItem.objects.get(slug="weekly-report-missing"),
                "free_text": "The Monday report did not arrive for the south zone campaign.",
                "status": SupportRequest.Status.TICKET_CREATED,
            },
        )

        ticket_1, created_1 = Ticket.objects.get_or_create(
            title="In-clinic collateral is not opening",
            requester_email=request_1.requester_email,
            department=campaign_ops,
            defaults={
                "description": request_1.free_text,
                "ticket_type": "In-clinic content issue",
                "user_type": "doctor",
                "source_system": Ticket.SourceSystem.CUSTOMER_SUPPORT,
                "priority": Ticket.Priority.HIGH,
                "campaign": cardio_campaign,
                "created_by": pm_user,
                "submitted_by": pm_user,
                "direct_recipient": campaign_ops.default_recipient,
                "current_assignee": campaign_ops.default_recipient,
                "requester_name": request_1.requester_name,
                "requester_company": request_1.requester_company,
                "support_request": request_1,
            },
        )
        ticket_2, created_2 = Ticket.objects.get_or_create(
            title="Weekly campaign report is missing",
            requester_email=request_2.requester_email,
            department=analytics,
            defaults={
                "description": request_2.free_text,
                "ticket_type": "Reporting issue",
                "user_type": "brand_manager",
                "source_system": Ticket.SourceSystem.CUSTOMER_SUPPORT,
                "priority": Ticket.Priority.MEDIUM,
                "campaign": cardio_campaign,
                "created_by": pm_user,
                "submitted_by": pm_user,
                "direct_recipient": analytics.default_recipient,
                "current_assignee": analytics.default_recipient,
                "requester_name": request_2.requester_name,
                "requester_company": request_2.requester_company,
                "support_request": request_2,
            },
        )
        manual_ticket, created_3 = Ticket.objects.get_or_create(
            title="Doctor not added to campaign",
            requester_email="meera.rep@example.com",
            department=campaign_ops,
            defaults={
                "description": "Please activate Dr. Karan Singh for the patient education campaign and confirm reporting visibility.",
                "ticket_type": "Campaign onboarding issue",
                "user_type": "field_rep",
                "source_system": Ticket.SourceSystem.PROJECT_MANAGER,
                "priority": Ticket.Priority.CRITICAL,
                "campaign": gluco_campaign,
                "created_by": pm_user,
                "submitted_by": field_rep_user_2,
                "direct_recipient": campaign_ops.default_recipient,
                "current_assignee": campaign_ops.default_recipient,
                "requester_name": "Rajan Menon",
                "requester_company": "GlucoCare",
            },
        )

        for ticket, support_item in [
            (ticket_1, SupportItem.objects.get(slug="in-clinic-collateral-not-opening")),
            (ticket_2, SupportItem.objects.get(slug="weekly-report-missing")),
            (manual_ticket, None),
        ]:
            classification = resolve_ticket_classification(
                title=ticket.title,
                ticket_type_name=None,
                ticket_category=None,
                ticket_type_definition=None,
                department=ticket.department,
                source_system=ticket.source_system,
                priority=ticket.priority,
                support_item=support_item,
            )
            ticket.ticket_category = classification["ticket_category"]
            ticket.ticket_type_definition = classification["ticket_type_definition"]
            ticket.ticket_type = classification["ticket_type_name"]
            ticket.save(update_fields=["ticket_category", "ticket_type_definition", "ticket_type", "updated_at"])

        for ticket, body, author in [
            (ticket_1, "Checked the content package and confirmed the PDF loads. Investigating the video embed issue.", operations_user),
            (ticket_2, "Analytics export rerun completed and the report will be reissued.", analytics_user),
            (manual_ticket, "Clinic enrollment is in progress. Awaiting doctor confirmation.", operations_user),
        ]:
            TicketNote.objects.get_or_create(ticket=ticket, author=author, body=body)

        if ticket_2.status != Ticket.Status.COMPLETED:
            change_ticket_status(ticket_2, analytics_user, Ticket.Status.COMPLETED)

        for campaign, group, clinic, form_fills, red_flags, patient_views, reports_sent, form_shares, patient_scans, follow_ups, reminders in [
            (cardio_campaign, bengaluru_group, clinic_a, 128, 39, 84, 28, 96, 104, 32, 24),
            (gluco_campaign, mumbai_group, clinic_b, 74, 22, 51, 12, 48, 67, 20, 14),
        ]:
            RedFlagSnapshot.objects.update_or_create(
                campaign=campaign,
                clinic_group=group,
                clinic=clinic,
                period_start=today - timedelta(days=30),
                period_end=today,
                defaults={
                    "form_fills": form_fills,
                    "red_flags_total": red_flags,
                    "patient_video_views": patient_views,
                    "reports_emailed_to_doctors": reports_sent,
                    "form_shares": form_shares,
                    "patient_scans": patient_scans,
                    "follow_ups_scheduled": follow_ups,
                    "reminders_sent": reminders,
                },
            )

        for campaign, group, clinic, video_views, completions, cluster_shares, scans, clicks in [
            (cardio_campaign, bengaluru_group, clinic_a, 214, 162, 44, 58, 19),
            (gluco_campaign, mumbai_group, clinic_b, 176, 131, 38, 43, 12),
        ]:
            PatientEducationSnapshot.objects.update_or_create(
                campaign=campaign,
                clinic_group=group,
                clinic=clinic,
                period_start=today - timedelta(days=30),
                period_end=today,
                defaults={
                    "video_views": video_views,
                    "video_completions": completions,
                    "cluster_shares": cluster_shares,
                    "patient_scans": scans,
                    "banner_clicks": clicks,
                },
            )

        for campaign, group, clinic, doctor, rep, shares, opens, pdf_reads, views, completions, downloads in [
            (cardio_campaign, bengaluru_group, clinic_a, doctor_a, field_rep_user, 68, 51, 37, 48, 29, 18),
            (gluco_campaign, mumbai_group, clinic_b, doctor_b, field_rep_user_2, 54, 39, 23, 35, 22, 14),
        ]:
            InClinicSnapshot.objects.update_or_create(
                campaign=campaign,
                clinic_group=group,
                clinic=clinic,
                period_start=today - timedelta(days=30),
                period_end=today,
                defaults={
                    "doctor": doctor,
                    "field_rep": rep,
                    "shares": shares,
                    "link_opens": opens,
                    "pdf_reads_completed": pdf_reads,
                    "video_views": views,
                    "video_completions": completions,
                    "pdf_downloads": downloads,
                },
            )

        for campaign, group, clinic, system_type, doctors_added, clinics_added, clinics_with_shares in [
            (cardio_campaign, bengaluru_group, clinic_a, AdoptionSnapshot.SystemType.RED_FLAG_ALERT, 16, 5, 4),
            (cardio_campaign, bengaluru_group, clinic_a, AdoptionSnapshot.SystemType.PATIENT_EDUCATION, 12, 5, 4),
            (cardio_campaign, bengaluru_group, clinic_a, AdoptionSnapshot.SystemType.IN_CLINIC, 9, 5, 4),
            (gluco_campaign, mumbai_group, clinic_b, AdoptionSnapshot.SystemType.PATIENT_EDUCATION, 11, 4, 3),
            (gluco_campaign, mumbai_group, clinic_b, AdoptionSnapshot.SystemType.IN_CLINIC, 7, 4, 2),
        ]:
            AdoptionSnapshot.objects.update_or_create(
                campaign=campaign,
                clinic_group=group,
                clinic=clinic,
                system_type=system_type,
                period_start=today - timedelta(days=30),
                period_end=today,
                defaults={
                    "doctors_added": doctors_added,
                    "clinics_added": clinics_added,
                    "clinics_with_shares": clinics_with_shares,
                },
            )

        for campaign, webinar_attendees, certificate_completed, onboarded_completed, non_onboarded_completed in [
            (cardio_campaign, 37, 14, 10, 4),
            (gluco_campaign, 29, 11, 7, 4),
        ]:
            ExternalGrowthSnapshot.objects.update_or_create(
                campaign=campaign,
                period_start=today - timedelta(days=30),
                period_end=today,
                defaults={
                    "webinar_attendees": webinar_attendees,
                    "certificate_completed": certificate_completed,
                    "onboarded_certificate_completed": onboarded_completed,
                    "non_onboarded_certificate_completed": non_onboarded_completed,
                },
            )

        self.stdout.write(self.style.SUCCESS("Seeded demo data for campaign management."))
