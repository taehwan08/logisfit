"""
웨이브 관리 시리얼라이저
"""
from rest_framework import serializers

from .models import (
    OutboundOrder, OutboundOrderItem,
    Wave, TotalPickList, TotalPickListDetail,
)


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


# ------------------------------------------------------------------
# 웨이브
# ------------------------------------------------------------------

class WaveCreateSerializer(serializers.Serializer):
    wave_time = serializers.RegexField(
        regex=r'^\d{2}:\d{2}$',
        help_text='HH:MM 형식 (예: 09:00)',
    )


class TotalPickListDetailSerializer(serializers.ModelSerializer):
    from_location_code = serializers.CharField(
        source='from_location.barcode', read_only=True,
    )
    to_location_code = serializers.CharField(
        source='to_location.barcode', read_only=True, default=None,
    )
    picked_by_name = serializers.CharField(
        source='picked_by.name', read_only=True, default=None,
    )

    class Meta:
        model = TotalPickListDetail
        fields = [
            'id', 'from_location', 'from_location_code',
            'to_location', 'to_location_code',
            'qty', 'picked_qty',
            'picked_by', 'picked_by_name', 'picked_at',
        ]


class TotalPickListSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_barcode = serializers.CharField(source='product.barcode', read_only=True)
    details = TotalPickListDetailSerializer(many=True, read_only=True)

    class Meta:
        model = TotalPickList
        fields = [
            'id', 'product', 'product_name', 'product_barcode',
            'total_qty', 'picked_qty', 'status', 'details',
        ]


class WaveListSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(
        source='created_by.name', read_only=True, default=None,
    )
    outbound_zone_code = serializers.CharField(
        source='outbound_zone.barcode', read_only=True, default=None,
    )

    class Meta:
        model = Wave
        fields = [
            'id', 'wave_id', 'status', 'wave_time',
            'outbound_zone', 'outbound_zone_code',
            'total_orders', 'total_skus',
            'picked_count', 'inspected_count', 'shipped_count',
            'created_by', 'created_by_name',
            'created_at', 'completed_at',
        ]


class WaveDetailSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(
        source='created_by.name', read_only=True, default=None,
    )
    outbound_zone_code = serializers.CharField(
        source='outbound_zone.barcode', read_only=True, default=None,
    )
    pick_lists = TotalPickListSerializer(many=True, read_only=True)
    orders = OutboundOrderListSerializer(many=True, read_only=True)

    class Meta:
        model = Wave
        fields = [
            'id', 'wave_id', 'status', 'wave_time',
            'outbound_zone', 'outbound_zone_code',
            'total_orders', 'total_skus',
            'picked_count', 'inspected_count', 'shipped_count',
            'created_by', 'created_by_name',
            'created_at', 'completed_at',
            'pick_lists', 'orders',
        ]


class WaveProgressSerializer(serializers.ModelSerializer):
    pick_lists = TotalPickListSerializer(many=True, read_only=True)
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Wave
        fields = [
            'wave_id', 'status',
            'total_orders', 'total_skus',
            'picked_count', 'inspected_count', 'shipped_count',
            'progress', 'pick_lists',
        ]

    def get_progress(self, obj):
        total = obj.total_orders or 1
        return {
            'picking': round(obj.picked_count / total * 100, 1),
            'inspection': round(obj.inspected_count / total * 100, 1),
            'shipping': round(obj.shipped_count / total * 100, 1),
        }


# ------------------------------------------------------------------
# PDA 피킹 스캔
# ------------------------------------------------------------------

class PickScanSerializer(serializers.Serializer):
    from_location_code = serializers.CharField(max_length=50)
    product_barcode = serializers.CharField(max_length=100)
    to_location_code = serializers.CharField(max_length=50)
    qty = serializers.IntegerField(min_value=1)


# ------------------------------------------------------------------
# PDA 검수
# ------------------------------------------------------------------

class InspectionOrderSerializer(serializers.ModelSerializer):
    """검수 대기 주문 목록용"""
    client_name = serializers.CharField(source='client.company_name', read_only=True)
    item_count = serializers.IntegerField(source='items.count', read_only=True)
    total_qty = serializers.SerializerMethodField()
    inspected_total = serializers.SerializerMethodField()

    class Meta:
        model = OutboundOrder
        fields = [
            'id', 'wms_order_id', 'status', 'recipient_name',
            'client', 'client_name', 'item_count',
            'total_qty', 'inspected_total',
        ]

    def get_total_qty(self, obj):
        return sum(i.qty for i in obj.items.all())

    def get_inspected_total(self, obj):
        return sum(i.inspected_qty for i in obj.items.all())


class InspectionItemSerializer(serializers.ModelSerializer):
    """검수 상세 품목"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_barcode = serializers.CharField(source='product.barcode', read_only=True)
    remaining = serializers.SerializerMethodField()

    class Meta:
        model = OutboundOrderItem
        fields = [
            'id', 'product', 'product_name', 'product_barcode',
            'qty', 'inspected_qty', 'remaining',
        ]

    def get_remaining(self, obj):
        return obj.qty - obj.inspected_qty


class InspectScanSerializer(serializers.Serializer):
    product_barcode = serializers.CharField(max_length=100)
