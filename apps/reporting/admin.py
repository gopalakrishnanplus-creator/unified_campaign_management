from django.contrib import admin

from .models import AdoptionSnapshot, ExternalGrowthSnapshot, InClinicSnapshot, PatientEducationSnapshot, RedFlagSnapshot


@admin.register(RedFlagSnapshot)
class RedFlagSnapshotAdmin(admin.ModelAdmin):
    list_display = ("campaign", "clinic", "period_start", "period_end", "form_fills", "red_flags_total")
    list_filter = ("campaign", "clinic_group")


@admin.register(PatientEducationSnapshot)
class PatientEducationSnapshotAdmin(admin.ModelAdmin):
    list_display = ("campaign", "clinic", "period_start", "period_end", "video_views", "video_completions")
    list_filter = ("campaign", "clinic_group")


@admin.register(InClinicSnapshot)
class InClinicSnapshotAdmin(admin.ModelAdmin):
    list_display = ("campaign", "clinic", "period_start", "period_end", "shares", "link_opens", "pdf_downloads")
    list_filter = ("campaign", "clinic_group")


@admin.register(AdoptionSnapshot)
class AdoptionSnapshotAdmin(admin.ModelAdmin):
    list_display = ("campaign", "clinic", "system_type", "doctors_added", "clinics_with_shares", "period_end")
    list_filter = ("campaign", "system_type")


@admin.register(ExternalGrowthSnapshot)
class ExternalGrowthSnapshotAdmin(admin.ModelAdmin):
    list_display = ("campaign", "period_start", "period_end", "webinar_attendees", "certificate_completed")
    list_filter = ("campaign",)
