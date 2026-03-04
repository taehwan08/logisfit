"""
웨이브 관리 시리얼라이저
"""
from rest_framework import serializers

from .models import OutboundOrder, OutboundOrderItem


# ------------------------------------------------------------------
# 주문 수신 (POST /api/v1/orders/)
# ------------------------------------------------------------------

class ShippingSerializer(serializers.Serializer):
    recipient_name = serializers.CharField(max_length=100)
    recipient_phone = serializers.CharField(max_length=20)
    recipient_address = serializers.CharField()
    recipient_zip = serializers.CharField(max_length=10, required=False, default='')
    shipping_memo = serializers.CharField(required=False, default='')


class OrderItemInputSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=50)
    qty = serializers.IntegerField(min_value=1)
    source_item_id = serializers.CharField(max_length=100, required=False, default='')


class OrderReceiveSerializer(serializers.Serializer):
    source = serializers.CharField(max_length=30)
    source_order_id = serializers.CharField(max_length=100)
    client_id = serializers.IntegerField()
    brand_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    order_type = serializers.ChoiceField(
        choices=OutboundOrder.ORDER_TYPE_CHOICES, default='B2C',
    )
    ordered_at = serializers.DateTimeField()
    shipping = ShippingSerializer()
    items = OrderItemInputSerializer(many=True, min_length=1)


# ------------------------------------------------------------------
# 조회용
# ------------------------------------------------------------------

class OutboundOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_barcode = serializers.CharField(source='product.barcode', read_only=True)

    class Meta:
        model = OutboundOrderItem
        fields = [
            'id', 'product', 'product_name', 'product_barcode',
            'qty', 'picked_qty', 'inspected_qty', 'source_item_id',
        ]


class OutboundOrderListSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.company_name', read_only=True)
    item_count = serializers.IntegerField(source='items.count', read_only=True)

    class Meta:
        model = OutboundOrder
        fields = [
            'id', 'wms_order_id', 'source', 'source_order_id',
            'client', 'client_name', 'order_type', 'status',
            'recipient_name', 'ordered_at', 'item_count',
            'hold_reason', 'created_at',
        ]


class OutboundOrderDetailSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.company_name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True, default=None)
    items = OutboundOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = OutboundOrder
        fields = [
            'id', 'wms_order_id', 'source', 'source_order_id',
            'client', 'client_name', 'brand', 'brand_name',
            'order_type', 'status',
            'recipient_name', 'recipient_phone', 'recipient_address',
            'recipient_zip', 'shipping_memo',
            'wave', 'tracking_number', 'carrier',
            'hold_reason', 'ordered_at', 'shipped_at',
            'items', 'created_at', 'updated_at',
        ]
