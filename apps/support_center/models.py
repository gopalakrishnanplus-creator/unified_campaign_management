from django.db import models
from django.utils.text import slugify


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
    class Status(models.TextChoices):
        SOLUTION_PROVIDED = "solution_provided", "Solution provided"
        TICKET_CREATED = "ticket_created", "Ticket created"

    user_type = models.CharField(max_length=24)
    requester_name = models.CharField(max_length=255)
    requester_email = models.EmailField()
    requester_company = models.CharField(max_length=255, blank=True)
    campaign = models.ForeignKey("campaigns.Campaign", null=True, blank=True, on_delete=models.SET_NULL, related_name="support_requests")
    item = models.ForeignKey(SupportItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="requests")
    subject = models.CharField(max_length=255)
    free_text = models.TextField(blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.TICKET_CREATED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.requester_name} / {self.subject}"
