from django.contrib import admin

from .models import BiometricEnrollRequest, BiometricTemplate, KioskDevice


@admin.register(KioskDevice)
class KioskDeviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'token_prefix', 'is_active', 'last_seen_at', 'created_at')
    readonly_fields = ('token_hash', 'token_prefix', 'created_at', 'last_seen_at', 'last_seen_ip')
    fields = ('name', 'is_active', 'token_prefix', 'last_seen_at', 'last_seen_ip', 'created_at')

    def has_add_permission(self, request):
        # Tokens can only be created via `manage.py kiosk_device create` —
        # the raw token is shown exactly once on the CLI and is never
        # stored or displayable here (only its hash is persisted).
        return False


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


@admin.register(BiometricEnrollRequest)
class BiometricEnrollRequestAdmin(admin.ModelAdmin):
    """
    Read-only admin — gives operational visibility into stuck/pending
    requests. Requests are only created by the web enroll flow and closed
    by the kiosk API or the "Cancelar solicitação" button.
    """
    list_display = ('employee', 'status', 'requested_by', 'requested_at', 'completed_at', 'fulfilled_by_device')
    list_filter = ('status',)
    readonly_fields = (
        'employee', 'status', 'requested_by', 'requested_at', 'completed_at', 'fulfilled_by_device',
    )
    search_fields = ('employee__name',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
