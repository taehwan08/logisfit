"""
이력 관리 시리얼라이저
"""
from rest_framework import serializers

from .models import InventoryTransaction


class InventoryTransactionSerializer(serializers.ModelSerializer):
    """재고 트랜잭션 시리얼라이저 (읽기 전용)"""

    client_name = serializers.CharField(source='client.company_name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True, default='')
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_barcode = serializers.CharField(source='product.barcode', read_only=True)
    from_location_barcode = serializers.CharField(
        source='from_location.barcode', read_only=True, default='',
    )
    to_location_barcode = serializers.CharField(
        source='to_location.barcode', read_only=True, default='',
    )
    transaction_type_display = serializers.CharField(
        source='get_transaction_type_display', read_only=True,
    )
    reference_type_display = serializers.CharField(
        source='get_reference_type_display', read_only=True,
    )
    performed_by_name = serializers.CharField(
        source='performed_by.name', read_only=True, default='',
    )

    class Meta:
        model = InventoryTransaction
        fields = [
            'id', 'timestamp',
            'client', 'client_name',
            'brand', 'brand_name',
            'product', 'product_name', 'product_barcode',
            'transaction_type', 'transaction_type_display',
            'from_location', 'from_location_barcode',
            'to_location', 'to_location_barcode',
            'qty', 'balance_after',
            'reference_type', 'reference_type_display',
            'reference_id', 'reason',
            'performed_by', 'performed_by_name',
        ]
        read_only_fields = fields
