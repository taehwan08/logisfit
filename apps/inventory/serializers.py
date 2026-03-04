"""
재고 관리 시리얼라이저
"""
from rest_framework import serializers

from .models import InventoryBalance, SafetyStock, ReservedStock, Product


class InventoryBalanceSerializer(serializers.ModelSerializer):
    """재고 잔량 시리얼라이저"""

    product_name = serializers.CharField(source='product.name', read_only=True)
    product_barcode = serializers.CharField(source='product.barcode', read_only=True)
    location_barcode = serializers.CharField(source='location.barcode', read_only=True)
    client_name = serializers.CharField(source='client.company_name', read_only=True)
    available_qty = serializers.SerializerMethodField()

    class Meta:
        model = InventoryBalance
        fields = [
            'id',
            'product', 'product_name', 'product_barcode',
            'location', 'location_barcode',
            'client', 'client_name',
            'on_hand_qty', 'allocated_qty', 'reserved_qty', 'available_qty',
            'lot_number', 'expiry_date',
            'updated_at',
        ]
        read_only_fields = ['updated_at']

    def get_available_qty(self, obj):
        return obj.available_qty


class SafetyStockSerializer(serializers.ModelSerializer):
    """안전재고 시리얼라이저"""

    product_name = serializers.CharField(source='product.name', read_only=True)
    client_name = serializers.CharField(source='client.company_name', read_only=True)

    class Meta:
        model = SafetyStock
        fields = [
            'id', 'product', 'product_name',
            'client', 'client_name',
            'min_qty', 'alert_enabled',
        ]


class ReservedStockSerializer(serializers.ModelSerializer):
    """예약재고 시리얼라이저"""

    product_name = serializers.CharField(source='product.name', read_only=True)
    client_name = serializers.CharField(source='client.company_name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True, default='')

    class Meta:
        model = ReservedStock
        fields = [
            'id', 'product', 'product_name',
            'client', 'client_name',
            'brand', 'brand_name',
            'reserved_qty', 'reason',
            'created_by', 'created_at', 'released_at', 'is_active',
        ]
        read_only_fields = ['created_at']


# ============================================================================
# 외부 제공 재고 API 시리얼라이저
# ============================================================================

class LocationStockSerializer(serializers.Serializer):
    """로케이션별 재고 상세"""
    location_code = serializers.CharField()
    zone_type = serializers.CharField()
    qty = serializers.IntegerField()


class InventoryDetailSerializer(serializers.Serializer):
    """상품별 5단 재고 집계 + 로케이션별 상세"""
    sku = serializers.CharField()
    product_name = serializers.CharField()
    client_id = serializers.IntegerField()
    brand_id = serializers.IntegerField(allow_null=True)
    on_hand = serializers.IntegerField()
    allocated = serializers.IntegerField()
    reserved = serializers.IntegerField()
    available = serializers.IntegerField()
    safety_stock = serializers.IntegerField(allow_null=True)
    is_below_safety = serializers.BooleanField()
    locations = LocationStockSerializer(many=True)


class InventoryBulkSerializer(serializers.Serializer):
    """상품별 재고 요약 (로케이션 상세 제외)"""
    sku = serializers.CharField()
    product_name = serializers.CharField()
    client_id = serializers.IntegerField()
    brand_id = serializers.IntegerField(allow_null=True)
    on_hand = serializers.IntegerField()
    allocated = serializers.IntegerField()
    reserved = serializers.IntegerField()
    available = serializers.IntegerField()
    safety_stock = serializers.IntegerField(allow_null=True)
    is_below_safety = serializers.BooleanField()
