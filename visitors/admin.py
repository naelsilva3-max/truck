from django.contrib import admin

from .models import Visit, Visitor


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'phone', 'created_at')
    search_fields = ('name', 'company', 'phone')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ('visitor', 'responsible', 'visit_date', 'arrival_time', 'actual_departure_time', 'id_verified')
    list_filter = ('id_verified', 'visit_date')
    search_fields = ('visitor__name', 'responsible__name')
    date_hierarchy = 'visit_date'
    raw_id_fields = ('visitor', 'responsible')
    readonly_fields = ('created_at', 'updated_at')
