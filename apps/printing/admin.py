"""
출력 관리 어드민
"""
from django.contrib import admin

from .models import Printer, Carrier, PrintJob


@admin.register(Printer)
class PrinterAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'ip_address', 'port', 'printer_type',
        'printer_language', 'is_active', 'location_description',
    ]
    list_filter = ['printer_type', 'is_active']
    search_fields = ['name', 'ip_address', 'location_description']


@admin.register(Carrier)
class CarrierAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'code']


@admin.register(PrintJob)
class PrintJobAdmin(admin.ModelAdmin):
    list_display = [
        'order', 'carrier', 'tracking_number',
        'printer', 'status', 'attempts', 'printed_at',
    ]
    list_filter = ['status', 'carrier']
    search_fields = ['tracking_number', 'order__wms_order_id']
    raw_id_fields = ['order', 'printer', 'printed_by']
