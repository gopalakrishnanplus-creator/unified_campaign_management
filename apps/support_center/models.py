import uuid

from django.db import models
from django.core.validators import FileExtensionValidator
from django.utils.text import slugify


def support_request_upload_to(instance, filename):
    return f"support-requests/{uuid.uuid4().hex}/{filename}"


class SupportSuperCategory(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "Support super categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class SupportPage(models.Model):
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    source_system = models.CharField(max_length=120, blank=True)
    source_flow = models.CharField(max_length=120, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["source_system", "source_flow", "display_order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_name = " ".join(part for part in [self.source_system, self.source_flow, self.name] if part).strip()
            self.slug = slugify(base_name or self.name)
        super().save(*args, **kwargs)


class SupportCategory(models.Model):
    super_category = models.ForeignKey(SupportSuperCategory, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]
        unique_together = ("super_category", "slug")

    def __str__(self):
        return f"{self.super_category} / {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class SupportItem(models.Model):
    class KnowledgeType(models.TextChoices):
        FAQ = "faq", "FAQ"
        TICKET_CASE = "ticket_case", "Ticket case"

    class ResponseMode(models.TextChoices):
        STANDARDIZED = "standardized", "Standardized solution"
        DIRECT_TICKET = "direct_ticket", "Direct ticket"

    page = models.ForeignKey(
        SupportPage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="items",
    )
    category = models.ForeignKey(SupportCategory, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True)
    summary = models.CharField(max_length=255, blank=True)
    knowledge_type = models.CharField(max_length=24, choices=KnowledgeType.choices, default=KnowledgeType.FAQ)
    response_mode = models.CharField(max_length=24, choices=ResponseMode.choices, default=ResponseMode.STANDARDIZED)
    solution_title = models.CharField(max_length=255, blank=True)
    solution_body = models.TextField(blank=True)
    associated_pdf_url = models.URLField(blank=True)
    associated_video_url = models.URLField(blank=True)
    ticket_department = models.ForeignKey(
        "ticketing.Department",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="support_items",
    )
    default_ticket_type = models.CharField(max_length=120, default="Customer support")
    source_system = models.CharField(max_length=120, default="Customer support")
    source_flow = models.CharField(max_length=120, blank=True)
    source_document = models.CharField(max_length=255, blank=True)
    source_page = models.PositiveIntegerField(null=True, blank=True)
    ticket_required = models.BooleanField(null=True, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_visible_to_doctors = models.BooleanField(default=True)
    is_visible_to_clinic_staff = models.BooleanField(default=True)
    is_visible_to_brand_managers = models.BooleanField(default=True)
    is_visible_to_field_reps = models.BooleanField(default=True)
    is_visible_to_patients = models.BooleanField(default=False)

    class Meta:
        ordering = ["display_order", "name"]
        unique_together = ("category", "slug")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def is_visible_for_role(self, user_type):
        mapping = {
            "doctor": self.is_visible_to_doctors,
            "clinic_staff": self.is_visible_to_clinic_staff,
            "brand_manager": self.is_visible_to_brand_managers,
            "field_rep": self.is_visible_to_field_reps,
            "patient": self.is_visible_to_patients,
        }
        return mapping.get(user_type, False)


class SupportRequest(models.Model):
    class DeviceType(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    class Device(models.TextChoices):
        PHONE = "phone", "Phone"
        PC = "pc", "PC"
        TABLET = "tablet", "Tablet"

    class Status(models.TextChoices):
        PENDING_PM_REVIEW = "pending_pm_review", "Pending PM review"
        SOLUTION_PROVIDED = "solution_provided", "Solution provided"
        TICKET_CREATED = "ticket_created", "Ticket created"

    queue_ticket_number = models.CharField(max_length=24, unique=True, editable=False, blank=True)
    user_type = models.CharField(max_length=24)
    requester_name = models.CharField(max_length=255)
    requester_email = models.EmailField()
    requester_number = models.CharField(max_length=32, blank=True)
    requester_company = models.CharField(max_length=255, blank=True)
    device_type = models.CharField(max_length=16, choices=DeviceType.choices, blank=True)
    device = models.CharField(max_length=16, choices=Device.choices, blank=True)
    campaign = models.ForeignKey("campaigns.Campaign", null=True, blank=True, on_delete=models.SET_NULL, related_name="support_requests")
    item = models.ForeignKey(SupportItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="requests")
    support_page = models.ForeignKey(
        SupportPage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requests",
    )
    support_super_category = models.ForeignKey(
        SupportSuperCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requests",
    )
    support_category = models.ForeignKey(
        SupportCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requests",
    )
    source_system = models.CharField(max_length=120, blank=True)
    source_flow = models.CharField(max_length=120, blank=True)
    subject = models.CharField(max_length=255)
    free_text = models.TextField(blank=True)
    uploaded_file = models.FileField(
        upload_to=support_request_upload_to,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "heic", "svg", "webp"])],
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.TICKET_CREATED)
    is_escalated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_escalated", "-created_at"]

    def __str__(self):
        return f"{self.queue_ticket_number or 'PMQ-PENDING'} / {self.requester_name} / {self.subject}"

    def save(self, *args, **kwargs):
        if not self.queue_ticket_number:
            while True:
                queue_ticket_number = f"PMQ-{uuid.uuid4().hex[:8].upper()}"
                if not type(self).objects.filter(queue_ticket_number=queue_ticket_number).exists():
                    self.queue_ticket_number = queue_ticket_number
                    break
        super().save(*args, **kwargs)

    @property
    def super_category(self):
        if self.support_super_category_id:
            return self.support_super_category
        return self.support_category.super_category if self.support_category_id else None

    @property
    def page_label(self):
        return self.support_page.name if self.support_page_id else ""

    @property
    def section_label(self):
        super_category = self.super_category
        return super_category.name if super_category else ""

    @property
    def screen_label(self):
        return self.support_category.name if self.support_category_id else self.page_label

    @property
    def priority_label(self):
        return "High Priority / Escalated" if self.is_escalated else "Standard"
