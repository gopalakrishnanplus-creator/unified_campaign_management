from django.db import models


class BaseSnapshot(models.Model):
    campaign = models.ForeignKey("campaigns.Campaign", on_delete=models.CASCADE, related_name="%(class)ss")
    clinic_group = models.ForeignKey("campaigns.ClinicGroup", on_delete=models.CASCADE, related_name="%(class)ss")
    clinic = models.ForeignKey("campaigns.Clinic", on_delete=models.CASCADE, related_name="%(class)ss")
    period_start = models.DateField()
    period_end = models.DateField()

    class Meta:
        abstract = True
        ordering = ["-period_end", "clinic__name"]


class RedFlagSnapshot(BaseSnapshot):
    form_fills = models.PositiveIntegerField(default=0)
    red_flags_total = models.PositiveIntegerField(default=0)
    patient_video_views = models.PositiveIntegerField(default=0)
    reports_emailed_to_doctors = models.PositiveIntegerField(default=0)
    form_shares = models.PositiveIntegerField(default=0)
    patient_scans = models.PositiveIntegerField(default=0)
    follow_ups_scheduled = models.PositiveIntegerField(default=0)
    reminders_sent = models.PositiveIntegerField(default=0)


class PatientEducationSnapshot(BaseSnapshot):
    video_views = models.PositiveIntegerField(default=0)
    video_completions = models.PositiveIntegerField(default=0)
    cluster_shares = models.PositiveIntegerField(default=0)
    patient_scans = models.PositiveIntegerField(default=0)
    banner_clicks = models.PositiveIntegerField(default=0)


class InClinicSnapshot(BaseSnapshot):
    field_rep = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    doctor = models.ForeignKey("campaigns.Doctor", null=True, blank=True, on_delete=models.SET_NULL)
    shares = models.PositiveIntegerField(default=0)
    link_opens = models.PositiveIntegerField(default=0)
    pdf_reads_completed = models.PositiveIntegerField(default=0)
    video_views = models.PositiveIntegerField(default=0)
    video_completions = models.PositiveIntegerField(default=0)
    pdf_downloads = models.PositiveIntegerField(default=0)


class AdoptionSnapshot(BaseSnapshot):
    class SystemType(models.TextChoices):
        RED_FLAG_ALERT = "red_flag_alert", "Red flag alert"
        PATIENT_EDUCATION = "patient_education", "Patient education"
        IN_CLINIC = "in_clinic", "In-clinic"

    system_type = models.CharField(max_length=24, choices=SystemType.choices)
    doctors_added = models.PositiveIntegerField(default=0)
    clinics_added = models.PositiveIntegerField(default=0)
    clinics_with_shares = models.PositiveIntegerField(default=0)


class ExternalGrowthSnapshot(models.Model):
    campaign = models.ForeignKey("campaigns.Campaign", on_delete=models.CASCADE, related_name="external_growth_snapshots")
    period_start = models.DateField()
    period_end = models.DateField()
    webinar_attendees = models.PositiveIntegerField(default=0)
    certificate_completed = models.PositiveIntegerField(default=0)
    onboarded_certificate_completed = models.PositiveIntegerField(default=0)
    non_onboarded_certificate_completed = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-period_end"]
