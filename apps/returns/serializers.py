"""
반품 관리 시리얼라이저
"""
from rest_framework import serializers

from .models import ReturnOrder, ReturnOrderItem


class ReturnOrderItemSerializer(serializers.ModelSerializer):
    """반품 품목"""

    product_name = serializers.CharField(source='product.name', read_only=True)
    product_barcode = serializers.CharField(source='product.barcode', read_only=True)
    disposition_display = serializers.CharField(
        source='get_disposition_display', read_only=True,
    )

    class Meta:
        model = ReturnOrderItem
        fields = [
            'id', 'product', 'product_name', 'product_barcode',
            'qty', 'good_qty', 'defect_qty',
            'disposition', 'disposition_display',
        ]


class ReturnOrderListSerializer(serializers.ModelSerializer):
    """반품주문 목록 (간략)"""

    client_name = serializers.CharField(source='client.company_name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True, default='')
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    return_reason_display = serializers.CharField(
        source='get_return_reason_display', read_only=True,
    )
    item_count = serializers.IntegerField(source='items.count', read_only=True)

    class Meta:
        model = ReturnOrder
        fields = [
            'id', 'return_id',
            'original_order',
            'client', 'client_name',
            'brand', 'brand_name',
            'status', 'status_display',
            'return_reason', 'return_reason_display',
            'notes', 'item_count',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['return_id', 'created_at', 'updated_at']


class ReturnOrderDetailSerializer(serializers.ModelSerializer):
    """반품주문 상세 (품목 포함)"""

    client_name = serializers.CharField(source='client.company_name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True, default='')
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    return_reason_display = serializers.CharField(
        source='get_return_reason_display', read_only=True,
    )
    items = ReturnOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = ReturnOrder
        fields = [
            'id', 'return_id',
            'original_order',
            'client', 'client_name',
            'brand', 'brand_name',
            'status', 'status_display',
            'return_reason', 'return_reason_display',
            'notes', 'items',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['return_id', 'status', 'created_at', 'updated_at']


class ReturnOrderCreateSerializer(serializers.ModelSerializer):
    """반품주문 생성 (품목 중첩)"""

    items = ReturnOrderItemSerializer(many=True)

    class Meta:
        model = ReturnOrder
        fields = [
            'client', 'brand', 'original_order',
            'return_reason', 'notes', 'items',
        ]

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        order = ReturnOrder.objects.create(**validated_data)
        for item_data in items_data:
            ReturnOrderItem.objects.create(return_order=order, **item_data)
        return order
