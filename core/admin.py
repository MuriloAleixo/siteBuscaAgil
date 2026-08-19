from __future__ import annotations

from django.contrib import admin

from core.models import DriveProfile


@admin.register(DriveProfile)
class DriveProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "folder_id", "storage_used_bytes", "storage_total_bytes", "last_synced_at")
    search_fields = ("user__username", "user__email", "folder_id")
    readonly_fields = ("last_synced_at",)
