from django.contrib import admin

from .models import SupportCategory, SupportItem, SupportPage, SupportRequest, SupportSuperCategory


class SupportCategoryInline(admin.TabularInline):
    model = SupportCategory
    extra = 0


@admin.register(SupportSuperCategory)
class SupportSuperCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "display_order", "is_active")
    inlines = (SupportCategoryInline,)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(SupportPage)
class SupportPageAdmin(admin.ModelAdmin):
    list_display = ("name", "source_system", "source_flow", "display_order", "is_active")
    list_filter = ("source_system", "source_flow", "is_active")
    search_fields = ("name", "source_system", "source_flow")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(SupportCategory)
class SupportCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "super_category", "display_order", "is_active")
    list_filter = ("super_category", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(SupportItem)
class SupportItemAdmin(admin.ModelAdmin):
    list_display = ("name", "page", "category", "source_system", "source_flow", "knowledge_type", "response_mode", "ticket_department", "is_active")
    list_filter = ("page", "source_system", "source_flow", "knowledge_type", "response_mode", "ticket_department", "is_active")
    search_fields = ("name", "summary", "solution_title", "source_system", "source_flow", "source_document", "page__name")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(SupportRequest)
class SupportRequestAdmin(admin.ModelAdmin):
    list_display = ("requester_name", "requester_email", "requester_number", "user_type", "campaign", "status", "created_at")
    list_filter = ("user_type", "status", "campaign")
    search_fields = ("requester_name", "requester_email", "requester_number", "subject", "free_text")
