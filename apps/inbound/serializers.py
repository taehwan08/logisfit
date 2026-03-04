"""
입고 관리 시리얼라이저
"""
from rest_framework import serializers

from .models import InboundOrder, InboundOrderItem


class InboundOrderItemSerializer(serializers.ModelSerializer):
    """입고 품목 시리얼라이저"""

    product_name = serializers.CharField(source='product.name', read_only=True)
    product_barcode = serializers.CharField(source='product.barcode', read_only=True)
    putaway_location_barcode = serializers.CharField(
        source='putaway_location.barcode', read_only=True, default='',
    )

    class Meta:
        model = InboundOrderItem
        fields = [
            'id', 'product', 'product_name', 'product_barcode',
            'expected_qty', 'inspected_qty', 'defect_qty',
            'putaway_location', 'putaway_location_barcode',
            'lot_number', 'expiry_date',
        ]


class InboundOrderListSerializer(serializers.ModelSerializer):
    """입고예정 목록 시리얼라이저 (간략)"""

    client_name = serializers.CharField(source='client.company_name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True, default='')
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    item_count = serializers.IntegerField(source='items.count', read_only=True)

    class Meta:
        model = InboundOrder
        fields = [
            'id', 'inbound_id',
            'client', 'client_name',
            'brand', 'brand_name',
            'status', 'status_display',
            'expected_date', 'notes',
            'item_count',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['inbound_id', 'created_at', 'updated_at']


class InboundOrderDetailSerializer(serializers.ModelSerializer):
    """입고예정 상세 시리얼라이저 (품목 포함)"""

    client_name = serializers.CharField(source='client.company_name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True, default='')
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items = InboundOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = InboundOrder
        fields = [
            'id', 'inbound_id',
            'client', 'client_name',
            'brand', 'brand_name',
            'status', 'status_display',
            'expected_date', 'notes',
            'items',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['inbound_id', 'status', 'created_at', 'updated_at']


class InboundOrderCreateSerializer(serializers.ModelSerializer):
    """입고예정 생성 시리얼라이저"""

    items = InboundOrderItemSerializer(many=True)

    class Meta:
        model = InboundOrder
        fields = [
            'client', 'brand', 'expected_date', 'notes', 'items',
        ]

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        order = InboundOrder.objects.create(**validated_data)
        for item_data in items_data:
            InboundOrderItem.objects.create(inbound_order=order, **item_data)
        return order


class InboundOrderUpdateSerializer(serializers.ModelSerializer):
    """입고예정 수정 시리얼라이저"""

    class Meta:
        model = InboundOrder
        fields = ['brand', 'expected_date', 'notes']
