from django.contrib import admin

from .models import Campaign, CampaignClinicEnrollment, CampaignFieldRepAssignment, Clinic, ClinicGroup, Doctor


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "brand_name", "status", "start_date", "end_date")
    list_filter = ("status", "has_in_clinic", "has_red_flag_alerts", "has_patient_education")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "brand_name", "support_contact_email")


@admin.register(ClinicGroup)
class ClinicGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "geography")
    search_fields = ("name", "geography")


@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = ("name", "clinic_group", "city", "state", "clinic_code")
    list_filter = ("clinic_group", "state")
    search_fields = ("name", "city", "clinic_code")


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("full_name", "clinic", "specialty", "is_onboarded", "is_growth_clinic_member")
    list_filter = ("is_onboarded", "is_growth_clinic_member", "clinic__clinic_group")
    search_fields = ("full_name", "clinic__name", "email")


@admin.register(CampaignFieldRepAssignment)
class CampaignFieldRepAssignmentAdmin(admin.ModelAdmin):
    list_display = ("campaign", "field_rep", "territory", "assigned_at", "is_active")
    list_filter = ("campaign", "is_active")
    search_fields = ("campaign__name", "field_rep__email")


@admin.register(CampaignClinicEnrollment)
class CampaignClinicEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("campaign", "clinic", "doctor", "source_system", "field_rep", "enrolled_on")
    list_filter = ("campaign", "source_system")
    search_fields = ("campaign__name", "clinic__name", "doctor__full_name", "field_rep__email")
