from django.contrib import admin

from .models import AttendanceRecord


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'entry_time', 'exit_time')
    list_filter = ('date', 'employee')
    search_fields = ('employee__name',)
    readonly_fields = ('created_at', 'date')
    ordering = ('-entry_time',)

    def has_delete_permission(self, request, obj=None):
        # Physical deletion is blocked at model level (Requirement 11.1)
        return False
