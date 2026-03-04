"""
반품 관리 어드민
"""
from django.contrib import admin

from .models import ReturnOrder, ReturnOrderItem


class ReturnOrderItemInline(admin.TabularInline):
    model = ReturnOrderItem
    extra = 1
    fields = ('product', 'qty', 'good_qty', 'defect_qty', 'disposition')
    raw_id_fields = ('product',)


@admin.register(ReturnOrder)
class ReturnOrderAdmin(admin.ModelAdmin):
    list_display = (
        'return_id', 'client', 'brand', 'status',
        'return_reason', 'item_count', 'created_by', 'created_at',
    )
    list_filter = ('status', 'return_reason', 'client')
    search_fields = ('return_id', 'client__company_name', 'notes')
    raw_id_fields = ('client', 'brand', 'created_by', 'original_order')
    readonly_fields = ('return_id', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'
    inlines = [ReturnOrderItemInline]
    list_per_page = 30

    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = '품목수'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'client', 'brand', 'created_by',
        ).prefetch_related('items')
