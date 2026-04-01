from django.contrib import admin

from .models import SupportCategory, SupportItem, SupportRequest, SupportSuperCategory


class SupportCategoryInline(admin.TabularInline):
    model = SupportCategory
    extra = 0


@admin.register(SupportSuperCategory)
class SupportSuperCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "display_order", "is_active")
    inlines = (SupportCategoryInline,)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(SupportCategory)
class SupportCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "super_category", "display_order", "is_active")
    list_filter = ("super_category", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(SupportItem)
class SupportItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "source_system", "source_flow", "knowledge_type", "response_mode", "ticket_department", "is_active")
    list_filter = ("source_system", "source_flow", "knowledge_type", "response_mode", "ticket_department", "is_active")
    search_fields = ("name", "summary", "solution_title", "source_system", "source_flow", "source_document")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(SupportRequest)
class SupportRequestAdmin(admin.ModelAdmin):
    list_display = ("requester_name", "requester_email", "user_type", "campaign", "status", "created_at")
    list_filter = ("user_type", "status", "campaign")
    search_fields = ("requester_name", "requester_email", "subject", "free_text")
