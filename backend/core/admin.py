from django.contrib import admin

from core.models import AIAgent, Group, GroupMembership, Message, Provider


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "adapter_type", "is_active", "has_key", "created_at")
    list_filter = ("adapter_type", "is_active")
    search_fields = ("name",)
    # Never expose the decrypted key blob in list view; edit form only.
    exclude = ()


@admin.register(AIAgent)
class AIAgentAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "model_id", "temperature", "is_active")
    list_filter = ("provider", "is_active")
    search_fields = ("name", "model_id")


class GroupMembershipInline(admin.TabularInline):
    model = GroupMembership
    extra = 0
    fields = ("agent", "turn_order", "is_muted", "priority_floor", "turn_count")


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "turn_mode", "speed_ms", "created_at")
    list_filter = ("status", "turn_mode")
    search_fields = ("name", "topic")
    inlines = [GroupMembershipInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("group", "role", "kind", "agent", "tokens_used", "created_at")
    list_filter = ("role", "kind", "group")
    search_fields = ("content",)
    readonly_fields = ("created_at", "updated_at")
