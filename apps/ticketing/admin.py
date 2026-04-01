from django.contrib import admin

from .models import Department, Ticket, TicketAttachment, TicketNote, TicketRoutingEvent


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "support_email", "default_recipient", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "support_email")


class TicketAttachmentInline(admin.TabularInline):
    model = TicketAttachment
    extra = 0


class TicketNoteInline(admin.StackedInline):
    model = TicketNote
    extra = 0


class TicketRoutingEventInline(admin.TabularInline):
    model = TicketRoutingEvent
    extra = 0
    readonly_fields = ("action", "actor", "from_user", "to_user", "description", "created_at")
    can_delete = False


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("ticket_number", "title", "department", "status", "priority", "current_assignee", "campaign", "created_at")
    list_filter = ("status", "priority", "department", "source_system", "user_type")
    search_fields = ("ticket_number", "title", "requester_email", "requester_name", "campaign__name")
    readonly_fields = ("ticket_number", "created_at", "updated_at", "resolved_at")
    inlines = (TicketRoutingEventInline, TicketNoteInline)


@admin.register(TicketNote)
class TicketNoteAdmin(admin.ModelAdmin):
    list_display = ("ticket", "author", "created_at")
    search_fields = ("ticket__ticket_number", "author__email", "body")
    inlines = (TicketAttachmentInline,)


@admin.register(TicketAttachment)
class TicketAttachmentAdmin(admin.ModelAdmin):
    list_display = ("note", "file", "created_at")
    search_fields = ("note__ticket__ticket_number",)
