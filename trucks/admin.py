from django.contrib import admin

from .models import Truck, TruckAssignment, TruckBrand, TruckModel


@admin.register(TruckBrand)
class TruckBrandAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(TruckModel)
class TruckModelAdmin(admin.ModelAdmin):
    list_display = ('brand', 'name')
    list_filter = ('brand',)
    search_fields = ('name', 'brand__name')


@admin.register(Truck)
class TruckAdmin(admin.ModelAdmin):
    list_display = ('license_plate', 'model', 'color', 'year', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('license_plate', 'model', 'chassis')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TruckAssignment)
class TruckAssignmentAdmin(admin.ModelAdmin):
    list_display = ('truck', 'driver', 'assigned_at', 'unassigned_at')
    list_filter = ('truck',)
    raw_id_fields = ('truck', 'driver')
    readonly_fields = ('assigned_at',)
