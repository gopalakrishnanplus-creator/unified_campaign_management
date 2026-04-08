import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


def ticket_attachment_upload_to(instance, filename):
    return f"ticketing/{instance.note.ticket.ticket_number}/{filename}"


class Department(models.Model):
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=24, unique=True)
    description = models.TextField(blank=True)
    support_email = models.EmailField(unique=True)
    external_directory_id = models.PositiveIntegerField(null=True, blank=True, unique=True)
    external_directory_name = models.CharField(max_length=120, blank=True)
    external_directory_code = models.CharField(max_length=64, blank=True)
    external_manager_email = models.EmailField(blank=True)
    default_recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="default_departments",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def display_name(self):
        return self.external_directory_name or self.name

    @property
    def display_code(self):
        return self.external_directory_code or self.code


class Ticket(models.Model):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        IN_PROCESS = "in_process", "In process"
        CANNOT_COMPLETE = "cannot_complete", "Cannot be completed"
        ON_HOLD = "on_hold", "On hold"
        NOT_STARTED = "not_started", "Not started"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class UserType(models.TextChoices):
        DOCTOR = "doctor", "Doctor"
        CLINIC_STAFF = "clinic_staff", "Clinic staff"
        BRAND_MANAGER = "brand_manager", "Brand manager"
        FIELD_REP = "field_rep", "Field rep"
        PATIENT = "patient", "Patient"
        INTERNAL = "internal", "Internal"

    class SourceSystem(models.TextChoices):
        CUSTOMER_SUPPORT = "customer_support", "Customer support"
        PROJECT_MANAGER = "project_manager", "Project management"
        IN_CLINIC = "in_clinic", "In-clinic"
        RED_FLAG_ALERT = "red_flag_alert", "Red flag alert"
        PATIENT_EDUCATION = "patient_education", "Patient education"
        MANUAL = "manual", "Manual"

    ticket_number = models.CharField(max_length=20, unique=True, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField()
    ticket_category = models.ForeignKey(
        "ticketing.TicketCategory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tickets",
    )
    ticket_type_definition = models.ForeignKey(
        "ticketing.TicketTypeDefinition",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tickets",
    )
    ticket_type = models.CharField(max_length=120)
    user_type = models.CharField(max_length=24, choices=UserType.choices, default=UserType.INTERNAL)
    source_system = models.CharField(max_length=24, choices=SourceSystem.choices, default=SourceSystem.MANUAL)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.NOT_STARTED)
    priority = models.CharField(max_length=16, choices=Priority.choices, default=Priority.MEDIUM)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="tickets")
    campaign = models.ForeignKey("campaigns.Campaign", null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_tickets",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="submitted_tickets",
    )
    direct_recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="direct_tickets",
    )
    current_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_tickets",
    )
    requester_name = models.CharField(max_length=255)
    requester_email = models.EmailField()
    requester_number = models.CharField(max_length=32, blank=True)
    requester_company = models.CharField(max_length=255, blank=True)
    external_ticket_number = models.CharField(max_length=20, blank=True)
    external_ticket_url = models.URLField(blank=True)
    external_ticket_status = models.CharField(max_length=32, blank=True)
    external_ticket_synced_at = models.DateTimeField(null=True, blank=True)
    external_ticket_error = models.TextField(blank=True)
    external_ticket_log = models.TextField(blank=True)
    support_request = models.OneToOneField(
        "support_center.SupportRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ticket_link",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    due_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.ticket_number

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if not self.ticket_number:
            self.ticket_number = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        if self.ticket_type_definition_id:
            if not self.ticket_type:
                self.ticket_type = self.ticket_type_definition.name
            if not self.ticket_category_id:
                self.ticket_category = self.ticket_type_definition.category
        if not self.direct_recipient_id and self.department.default_recipient_id:
            self.direct_recipient = self.department.default_recipient
        if not self.current_assignee_id and self.direct_recipient_id:
            self.current_assignee = self.direct_recipient
        if not self.requester_number:
            for user in (self.created_by, self.submitted_by):
                if user and user.phone_number:
                    self.requester_number = user.phone_number
                    break
        if self.status == self.Status.COMPLETED and not self.resolved_at:
            self.resolved_at = timezone.now()
        if self.status != self.Status.COMPLETED:
            self.resolved_at = None
        super().save(*args, **kwargs)
        if is_new:
            TicketRoutingEvent.objects.create(
                ticket=self,
                action=TicketRoutingEvent.Action.ASSIGNED,
                actor=self.created_by,
                from_user=None,
                to_user=self.direct_recipient,
                description="Ticket created and assigned.",
            )

    @property
    def ageing_days(self):
        return (timezone.now() - self.created_at).days

    @property
    def resolution_hours(self):
        if not self.resolved_at:
            return None
        delta = self.resolved_at - self.created_at
        return round(delta.total_seconds() / 3600, 2)

    def can_change_status(self, user):
        return bool(user and user.is_authenticated and (user == self.direct_recipient or user.is_superuser))

    def can_view(self, user):
        if not user or not user.is_authenticated:
            return False
        return user.is_superuser or user.is_project_manager or user in {
            self.direct_recipient,
            self.current_assignee,
            self.created_by,
            self.submitted_by,
        }

    @property
    def priority_badge_class(self):
        return {
            self.Priority.LOW: "priority-low",
            self.Priority.MEDIUM: "priority-medium",
            self.Priority.HIGH: "priority-high",
            self.Priority.CRITICAL: "priority-critical",
        }.get(self.priority, "priority-medium")

    @property
    def status_badge_class(self):
        return {
            self.Status.NOT_STARTED: "status-not-started",
            self.Status.IN_PROCESS: "status-in-process",
            self.Status.ON_HOLD: "status-on-hold",
            self.Status.CANNOT_COMPLETE: "status-cannot-complete",
            self.Status.COMPLETED: "status-completed",
        }.get(self.status, "status-not-started")


class TicketCategory(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "Ticket categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class TicketTypeDefinition(models.Model):
    category = models.ForeignKey(TicketCategory, on_delete=models.CASCADE, related_name="ticket_types")
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, blank=True)
    description = models.TextField(blank=True)
    default_priority = models.CharField(max_length=16, choices=Ticket.Priority.choices, default=Ticket.Priority.MEDIUM)
    default_department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ticket_types",
    )
    default_source_system = models.CharField(
        max_length=24,
        choices=Ticket.SourceSystem.choices,
        default=Ticket.SourceSystem.MANUAL,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category__display_order", "category__name", "name"]
        unique_together = ("category", "slug")
        verbose_name = "Ticket type"
        verbose_name_plural = "Ticket types"

    def __str__(self):
        return f"{self.category.name} / {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class TicketRoutingEvent(models.Model):
    class Action(models.TextChoices):
        ASSIGNED = "assigned", "Assigned"
        DELEGATED = "delegated", "Delegated"
        RETURNED = "returned", "Returned to sender"
        STATUS_CHANGED = "status_changed", "Status changed"

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="routing_events")
    action = models.CharField(max_length=24, choices=Action.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ticket_actions",
    )
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ticket_events_from",
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ticket_events_to",
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class TicketNote(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ticket_notes")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.ticket.ticket_number} / {self.author.email}"


class TicketAttachment(models.Model):
    note = models.ForeignKey(TicketNote, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(
        upload_to=ticket_attachment_upload_to,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf", "png", "jpg", "jpeg", "heic", "svg", "webp", "doc", "docx", "xls", "xlsx", "txt"]
            )
        ],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
