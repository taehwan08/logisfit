from django.contrib import admin

from .models import Product, Location, InventorySession, InventoryRecord


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('barcode', 'name', 'display_name', 'created_at', 'updated_at')
    search_fields = ('barcode', 'name', 'display_name')
    ordering = ('name',)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('barcode', 'name', 'zone', 'created_at')
    search_fields = ('barcode', 'name')
    list_filter = ('zone',)


@admin.register(InventorySession)
class InventorySessionAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'started_at', 'ended_at', 'started_by')
    list_filter = ('status',)
    search_fields = ('name',)


@admin.register(InventoryRecord)
class InventoryRecordAdmin(admin.ModelAdmin):
    list_display = ('session', 'location', 'barcode', 'product_name', 'quantity', 'worker', 'created_at')
    list_filter = ('session',)
    search_fields = ('barcode', 'product_name', 'location__barcode')
