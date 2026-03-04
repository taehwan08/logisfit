"""
웨이브 관리 어드민
"""
from django.contrib import admin

from .models import (
    Wave, OutboundOrder, OutboundOrderItem,
    TotalPickList, TotalPickListDetail,
)


class OutboundOrderItemInline(admin.TabularInline):
    model = OutboundOrderItem
    extra = 0
    readonly_fields = ('picked_qty', 'inspected_qty')


class TotalPickListDetailInline(admin.TabularInline):
    model = TotalPickListDetail
    extra = 0
    readonly_fields = ('picked_by', 'picked_at')


class TotalPickListInline(admin.TabularInline):
    model = TotalPickList
    extra = 0
    readonly_fields = ('picked_qty',)
    show_change_link = True


@admin.register(Wave)
class WaveAdmin(admin.ModelAdmin):
    list_display = (
        'wave_id', 'status', 'wave_time', 'total_orders',
        'total_skus', 'picked_count', 'shipped_count', 'created_at',
    )
    list_filter = ('status',)
    search_fields = ('wave_id',)
    readonly_fields = ('wave_id', 'created_at', 'completed_at')
    inlines = [TotalPickListInline]


@admin.register(TotalPickList)
class TotalPickListAdmin(admin.ModelAdmin):
    list_display = ('wave', 'product', 'total_qty', 'picked_qty', 'status')
    list_filter = ('status', 'wave')
    inlines = [TotalPickListDetailInline]


@admin.register(OutboundOrder)
class OutboundOrderAdmin(admin.ModelAdmin):
    list_display = (
        'wms_order_id', 'source', 'source_order_id', 'client',
        'order_type', 'status', 'recipient_name', 'wave', 'ordered_at',
    )
    list_filter = ('status', 'order_type', 'source', 'client')
    search_fields = ('wms_order_id', 'source_order_id', 'recipient_name')
    readonly_fields = ('wms_order_id', 'created_at', 'updated_at')
    date_hierarchy = 'ordered_at'
    inlines = [OutboundOrderItemInline]
