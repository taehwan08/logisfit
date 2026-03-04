"""
웨이브 관리 뷰
"""
import logging

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clients.models import Client, Brand
from apps.inventory.models import Product
from apps.inventory.services import InventoryService
from apps.inventory.exceptions import InsufficientStockError

from .models import OutboundOrder, OutboundOrderItem, Wave
from .permissions import IsOfficeStaff
from .serializers import (
    OrderReceiveSerializer,
    OutboundOrderDetailSerializer,
    WaveCreateSerializer,
    WaveListSerializer,
    WaveDetailSerializer,
    WaveProgressSerializer,
)
from .services import WaveService

logger = logging.getLogger(__name__)


def _resolve_product_by_sku(sku):
    """SKU(바코드)로 상품 조회.

    1) Product.barcode 매칭
    2) ProductBarcode 테이블 매칭
    """
    product = Product.objects.filter(barcode=sku).first()
    if product:
        return product

    from apps.inventory.models import ProductBarcode
    pb = ProductBarcode.objects.select_related('product').filter(barcode=sku).first()
    if pb:
        return pb.product

    return None


class OrderReceiveView(APIView):
    """주문 수신 API

    POST /api/v1/orders/
    외부 시스템(사방넷, 카페24, OMS 등)에서 주문을 수신합니다.
    자동으로 재고 할당을 시도하여 ALLOCATED 또는 HELD 상태로 전환합니다.
    """

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = OrderReceiveSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Client 확인
        try:
            client = Client.objects.get(pk=data['client_id'])
        except Client.DoesNotExist:
            return Response(
                {'error': '거래처를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Brand 확인 (선택)
        brand = None
        if data.get('brand_id'):
            brand = Brand.objects.filter(
                pk=data['brand_id'], client=client,
            ).first()
            if not brand:
                return Response(
                    {'error': '브랜드를 찾을 수 없습니다.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        # 상품 조회
        shipping = data['shipping']
        items_data = data['items']
        resolved_items = []
        for item in items_data:
            product = _resolve_product_by_sku(item['sku'])
            if not product:
                return Response(
                    {'error': f"상품을 찾을 수 없습니다: {item['sku']}"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            resolved_items.append({
                'product': product,
                'qty': item['qty'],
                'source_item_id': item.get('source_item_id', ''),
            })

        # OutboundOrder 생성
        order = OutboundOrder.objects.create(
            source=data['source'],
            source_order_id=data['source_order_id'],
            client=client,
            brand=brand,
            order_type=data.get('order_type', 'B2C'),
            ordered_at=data['ordered_at'],
            recipient_name=shipping['recipient_name'],
            recipient_phone=shipping['recipient_phone'],
            recipient_address=shipping['recipient_address'],
            recipient_zip=shipping.get('recipient_zip', ''),
            shipping_memo=shipping.get('shipping_memo', ''),
        )

        # OutboundOrderItem 생성
        for item in resolved_items:
            OutboundOrderItem.objects.create(
                order=order,
                product=item['product'],
                qty=item['qty'],
                source_item_id=item['source_item_id'],
            )

        # 재고 할당 시도
        hold_reasons = []
        for item in resolved_items:
            try:
                InventoryService.allocate_stock(
                    product=item['product'],
                    client=client,
                    qty=item['qty'],
                    reference_id=order.wms_order_id,
                    performed_by=request.user,
                    brand=brand,
                )
            except InsufficientStockError as e:
                hold_reasons.append(
                    f"{item['product'].name}: 요청 {e.requested}, 가용 {e.available}"
                )

        if hold_reasons:
            order.status = 'HELD'
            order.hold_reason = '; '.join(hold_reasons)
            order.save(update_fields=['status', 'hold_reason', 'updated_at'])
            # 성공한 할당은 롤백하지 않음 — 부분 할당 허용하지 않으므로 전체 롤백
            # 트랜잭션 내에서 할당 해제
            for item in resolved_items:
                try:
                    InventoryService.deallocate_stock(
                        product=item['product'],
                        client=client,
                        qty=item['qty'],
                        reference_id=order.wms_order_id,
                        performed_by=request.user,
                        brand=brand,
                    )
                except InsufficientStockError:
                    pass  # 할당이 안 된 건이므로 무시
        else:
            order.status = 'ALLOCATED'
            order.save(update_fields=['status', 'updated_at'])

        result = OutboundOrderDetailSerializer(order).data
        return Response(result, status=status.HTTP_201_CREATED)


class OrderCancelView(APIView):
    """주문 취소 API

    POST /api/v1/orders/{wms_order_id}/cancel/
    할당된 재고를 해제하고 주문을 취소합니다.
    """

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, wms_order_id):
        try:
            order = OutboundOrder.objects.get(wms_order_id=wms_order_id)
        except OutboundOrder.DoesNotExist:
            return Response(
                {'error': '주문을 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status in ('SHIPPED', 'CANCELLED'):
            return Response(
                {'error': f'이미 {order.get_status_display()} 상태입니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 할당된 상태라면 할당 해제
        if order.status == 'ALLOCATED':
            for item in order.items.select_related('product').all():
                try:
                    InventoryService.deallocate_stock(
                        product=item.product,
                        client=order.client,
                        qty=item.qty,
                        reference_id=order.wms_order_id,
                        performed_by=request.user,
                        brand=order.brand,
                    )
                except InsufficientStockError:
                    logger.warning(
                        'Cancel dealloc failed: order=%s product=%s',
                        order.wms_order_id, item.product.barcode,
                    )

        order.status = 'CANCELLED'
        order.save(update_fields=['status', 'updated_at'])

        result = OutboundOrderDetailSerializer(order).data
        return Response(result)


# ------------------------------------------------------------------
# 웨이브 API
# ------------------------------------------------------------------

class WaveCreateView(APIView):
    """웨이브 생성 API

    POST /api/v1/waves/create/
    ALLOCATED + wave 미배정 주문을 수집하여 웨이브를 생성합니다.
    """

    permission_classes = [IsOfficeStaff]

    def post(self, request):
        serializer = WaveCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            wave = WaveService.create_wave(
                wave_time=serializer.validated_data['wave_time'],
                created_by=request.user,
            )
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = WaveDetailSerializer(wave).data
        return Response(result, status=status.HTTP_201_CREATED)


class WaveListView(APIView):
    """웨이브 목록 API

    GET /api/v1/waves/
    """

    permission_classes = [IsOfficeStaff]

    def get(self, request):
        waves = Wave.objects.select_related('outbound_zone', 'created_by').all()

        # 상태 필터
        wave_status = request.query_params.get('status')
        if wave_status:
            waves = waves.filter(status=wave_status)

        data = WaveListSerializer(waves, many=True).data
        return Response(data)


class WaveDetailView(APIView):
    """웨이브 상세 API

    GET /api/v1/waves/{wave_id}/
    """

    permission_classes = [IsOfficeStaff]

    def get(self, request, wave_id):
        try:
            wave = (
                Wave.objects
                .select_related('outbound_zone', 'created_by')
                .prefetch_related(
                    'pick_lists__product',
                    'pick_lists__details__from_location',
                    'pick_lists__details__to_location',
                    'pick_lists__details__picked_by',
                    'orders__client',
                )
                .get(wave_id=wave_id)
            )
        except Wave.DoesNotExist:
            return Response(
                {'error': '웨이브를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(WaveDetailSerializer(wave).data)


class WaveProgressView(APIView):
    """웨이브 진행률 API

    GET /api/v1/waves/{wave_id}/progress/
    """

    permission_classes = [IsOfficeStaff]

    def get(self, request, wave_id):
        try:
            wave = (
                Wave.objects
                .prefetch_related(
                    'pick_lists__product',
                    'pick_lists__details__from_location',
                    'pick_lists__details__to_location',
                    'pick_lists__details__picked_by',
                )
                .get(wave_id=wave_id)
            )
        except Wave.DoesNotExist:
            return Response(
                {'error': '웨이브를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(WaveProgressSerializer(wave).data)
