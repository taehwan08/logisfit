"""
이력 관리 어드민
"""
from django.contrib import admin

from .models import InventoryTransaction


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    """재고 트랜잭션 관리 (읽기 전용)"""

    list_display = (
        'timestamp', 'client', 'product',
        'transaction_type', 'from_location', 'to_location',
        'qty', 'balance_after',
        'reference_type', 'reference_id', 'performed_by',
    )
    list_filter = ('transaction_type', 'reference_type', 'client', 'timestamp')
    search_fields = (
        'product__name', 'product__barcode',
        'reference_id', 'reason',
        'client__company_name',
    )
    raw_id_fields = ('client', 'brand', 'product', 'from_location', 'to_location', 'performed_by')
    readonly_fields = (
        'timestamp', 'client', 'brand', 'product',
        'transaction_type', 'from_location', 'to_location',
        'qty', 'balance_after',
        'reference_type', 'reference_id', 'reason', 'performed_by',
    )
    list_per_page = 50
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'client', 'brand', 'product',
            'from_location', 'to_location', 'performed_by',
        )
