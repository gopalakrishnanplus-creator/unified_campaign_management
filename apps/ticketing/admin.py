from django.contrib import admin

from .models import Department, Ticket, TicketAttachment, TicketCategory, TicketNote, TicketRoutingEvent, TicketTypeDefinition


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
    list_display = (
        "ticket_number",
        "title",
        "ticket_category",
        "ticket_type",
        "department",
        "status",
        "priority",
        "current_assignee",
        "campaign",
        "created_at",
    )
    list_filter = ("status", "priority", "department", "ticket_category", "source_system", "user_type")
    search_fields = ("ticket_number", "title", "requester_email", "requester_name", "campaign__name")
    readonly_fields = ("ticket_number", "created_at", "updated_at", "resolved_at")
    inlines = (TicketRoutingEventInline, TicketNoteInline)


@admin.register(TicketCategory)
class TicketCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "display_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")


@admin.register(TicketTypeDefinition)
class TicketTypeDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "default_department", "default_priority", "default_source_system", "is_active")
    list_filter = ("category", "default_priority", "default_source_system", "is_active")
    search_fields = ("name", "description", "category__name")


@admin.register(TicketNote)
class TicketNoteAdmin(admin.ModelAdmin):
    list_display = ("ticket", "author", "created_at")
    search_fields = ("ticket__ticket_number", "author__email", "body")
    inlines = (TicketAttachmentInline,)


@admin.register(TicketAttachment)
class TicketAttachmentAdmin(admin.ModelAdmin):
    list_display = ("note", "file", "created_at")
    search_fields = ("note__ticket__ticket_number",)
