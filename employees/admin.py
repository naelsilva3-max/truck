from django.contrib import admin
from .models import Employee


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'department', 'phone', 'cpf', 'hire_date', 'is_driver', 'is_active', 'created_at')
    list_filter = ('is_driver', 'is_active', 'department')
    search_fields = ('name', 'role', 'department', 'phone', 'cpf', 'rg')
    date_hierarchy = 'hire_date'
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('name', 'role', 'department', 'phone', 'hire_date')
        }),
        ('Documentos e Endereço', {
            'fields': ('rg', 'cpf', 'address', 'cep')
        }),
        ('Status', {
            'fields': ('is_driver', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
