from django.contrib import admin

from .models import SystemLog, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'cpf', 'email_verified')
    list_filter = ('role', 'email_verified')
    search_fields = ('user__username', 'cpf')
    raw_id_fields = ('user',)


@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    """Read-only admin — SystemLog is an append-only audit trail (see model's
    save()/delete() overrides); entries are only ever created via log_action()."""
    list_display = ('timestamp', 'username', 'action', 'description', 'ip_address')
    list_filter = ('action',)
    search_fields = ('username', 'description', 'path')
    date_hierarchy = 'timestamp'
    readonly_fields = ('user', 'username', 'action', 'description', 'timestamp', 'ip_address', 'path')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
