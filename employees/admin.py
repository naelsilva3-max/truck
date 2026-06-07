from django.contrib import admin
from .models import BiometricTemplate, Employee


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'department', 'phone', 'hire_date', 'is_driver', 'is_active', 'created_at')
    list_filter = ('is_driver', 'is_active', 'department')
    search_fields = ('name', 'role', 'department', 'phone')
    date_hierarchy = 'hire_date'
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('name', 'role', 'department', 'phone', 'hire_date')
        }),
        ('Status', {
            'fields': ('is_driver', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(BiometricTemplate)
class BiometricTemplateAdmin(admin.ModelAdmin):
    """
    Read-only admin for BiometricTemplate.
    The raw template bytes are NEVER displayed — only metadata is shown.
    """
    list_display = ('employee', 'finger_index', 'template_size_bytes', 'enrolled_at', 'updated_at')
    readonly_fields = ('employee', 'finger_index', 'template_size_bytes', 'enrolled_at', 'updated_at')
    search_fields = ('employee__name',)
    ordering = ('employee__name',)

    # Exclude the raw 'template' field from all admin views
    exclude = ('template',)

    def template_size_bytes(self, obj):
        """Display template size without exposing its contents."""
        if obj.template:
            return f'{len(bytes(obj.template))} bytes'
        return '—'
    template_size_bytes.short_description = 'Tamanho do template'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
