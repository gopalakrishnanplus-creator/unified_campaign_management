from django.db import models
from django.utils.text import slugify


class Campaign(models.Model):
    class Status(models.TextChoices):
        PLANNING = "planning", "Planning"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    brand_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PLANNING)
    geography = models.CharField(max_length=120, default="India")
    start_date = models.DateField()
    end_date = models.DateField()
    has_in_clinic = models.BooleanField(default=True)
    has_red_flag_alerts = models.BooleanField(default=True)
    has_patient_education = models.BooleanField(default=True)
    sponsor_banner_url = models.URLField(blank=True)
    support_contact_email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ClinicGroup(models.Model):
    name = models.CharField(max_length=255)
    geography = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("name", "geography")

    def __str__(self):
        return self.name


class Clinic(models.Model):
    name = models.CharField(max_length=255)
    clinic_group = models.ForeignKey(ClinicGroup, on_delete=models.CASCADE, related_name="clinics")
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=120)
    clinic_code = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.city})"


class Doctor(models.Model):
    full_name = models.CharField(max_length=255)
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="doctors")
    specialty = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    is_onboarded = models.BooleanField(default=True)
    is_growth_clinic_member = models.BooleanField(default=False)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class CampaignFieldRepAssignment(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="field_rep_assignments")
    field_rep = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="campaign_assignments")
    territory = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateField()

    class Meta:
        unique_together = ("campaign", "field_rep")
        ordering = ["campaign__name", "field_rep__email"]

    def __str__(self):
        return f"{self.campaign} / {self.field_rep}"


class CampaignClinicEnrollment(models.Model):
    class SourceSystem(models.TextChoices):
        IN_CLINIC = "in_clinic", "In-clinic"
        RED_FLAG_ALERT = "red_flag_alert", "Red flag alert"
        PATIENT_EDUCATION = "patient_education", "Patient education"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="clinic_enrollments")
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="campaign_enrollments")
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="campaign_enrollments")
    field_rep = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    source_system = models.CharField(max_length=24, choices=SourceSystem.choices)
    enrolled_on = models.DateField()

    class Meta:
        ordering = ["campaign__name", "clinic__name", "doctor__full_name"]

    def __str__(self):
        return f"{self.campaign} / {self.doctor}"
