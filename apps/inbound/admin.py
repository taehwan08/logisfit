"""
입고 관리 어드민
"""
from django.contrib import admin

from .models import InboundOrder, InboundOrderItem


class InboundOrderItemInline(admin.TabularInline):
    """입고 품목 인라인"""
    model = InboundOrderItem
    extra = 1
    fields = (
        'product', 'expected_qty', 'inspected_qty', 'defect_qty',
        'putaway_location', 'lot_number', 'expiry_date',
    )
    raw_id_fields = ('product', 'putaway_location')


@admin.register(InboundOrder)
class InboundOrderAdmin(admin.ModelAdmin):
    list_display = (
        'inbound_id', 'client', 'brand', 'status',
        'expected_date', 'item_count', 'created_by', 'created_at',
    )
    list_filter = ('status', 'client', 'expected_date')
    search_fields = ('inbound_id', 'client__company_name', 'notes')
    raw_id_fields = ('client', 'brand', 'created_by')
    readonly_fields = ('inbound_id', 'created_at', 'updated_at')
    date_hierarchy = 'expected_date'
    inlines = [InboundOrderItemInline]
    list_per_page = 30

    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = '품목수'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'client', 'brand', 'created_by',
        ).prefetch_related('items')
