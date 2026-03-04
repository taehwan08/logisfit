"""
웨이브 관리 어드민
"""
from django.contrib import admin

from .models import Wave, OutboundOrder, OutboundOrderItem


class OutboundOrderItemInline(admin.TabularInline):
    model = OutboundOrderItem
    extra = 0
    readonly_fields = ('picked_qty', 'inspected_qty')


@admin.register(Wave)
class WaveAdmin(admin.ModelAdmin):
    list_display = ('wave_id', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('wave_id',)


@admin.register(OutboundOrder)
class OutboundOrderAdmin(admin.ModelAdmin):
    list_display = (
        'wms_order_id', 'source', 'source_order_id', 'client',
        'order_type', 'status', 'recipient_name', 'ordered_at',
    )
    list_filter = ('status', 'order_type', 'source', 'client')
    search_fields = ('wms_order_id', 'source_order_id', 'recipient_name')
    readonly_fields = ('wms_order_id', 'created_at', 'updated_at')
    date_hierarchy = 'ordered_at'
    inlines = [OutboundOrderItemInline]
