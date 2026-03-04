"""
웨이브 관리 뷰
"""
import logging

from django.db import transaction
from django.db.models import F as models_F
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clients.models import Client, Brand
from apps.inventory.models import Product, Location, InventoryBalance
from apps.inventory.services import InventoryService
from apps.inventory.exceptions import InsufficientStockError

from .models import (
    OutboundOrder, OutboundOrderItem, Wave,
    TotalPickList, TotalPickListDetail,
)
from .permissions import IsOfficeStaff, IsFieldStaff
from .serializers import (
    OrderReceiveSerializer,
    OutboundOrderDetailSerializer,
    WaveCreateSerializer,
    WaveListSerializer,
    WaveDetailSerializer,
    WaveProgressSerializer,
    TotalPickListSerializer,
    PickScanSerializer,
    InspectionOrderSerializer,
    InspectionItemSerializer,
    InspectScanSerializer,
    ShipConfirmSerializer,
)
from .services import WaveService, ShipmentService
from .signals import order_inspected

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


# ------------------------------------------------------------------
# PDA 토탈피킹 API
# ------------------------------------------------------------------

def _resolve_product_by_barcode(barcode):
    """바코드로 상품 조회 (ProductBarcode 우선, Product.barcode 폴백)"""
    from apps.inventory.models import ProductBarcode
    pb = ProductBarcode.objects.select_related('product').filter(barcode=barcode).first()
    if pb:
        return pb.product
    return Product.objects.filter(barcode=barcode).first()


def _pick_error(code, message, http_status=status.HTTP_400_BAD_REQUEST):
    return Response({'error': code, 'message': message}, status=http_status)


class PickListView(APIView):
    """피킹리스트 조회 (PDA 화면용)

    GET /api/v1/waves/{wave_id}/picklist/
    PENDING, IN_PROGRESS 상태의 TotalPickList만 반환.
    """

    permission_classes = [IsFieldStaff]

    def get(self, request, wave_id):
        try:
            wave = Wave.objects.get(wave_id=wave_id)
        except Wave.DoesNotExist:
            return Response(
                {'error': '웨이브를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        pick_lists = (
            wave.pick_lists
            .filter(status__in=['PENDING', 'IN_PROGRESS'])
            .select_related('product')
            .prefetch_related(
                'details__from_location',
                'details__to_location',
                'details__picked_by',
            )
        )
        return Response({
            'wave_id': wave.wave_id,
            'wave_status': wave.status,
            'outbound_zone_code': (
                wave.outbound_zone.barcode if wave.outbound_zone else None
            ),
            'pick_lists': TotalPickListSerializer(pick_lists, many=True).data,
        })


class PickScanView(APIView):
    """피킹 스캔 처리

    POST /api/v1/waves/{wave_id}/pick/
    PDA에서 바코드 스캔 후 피킹 확인 요청.
    """

    permission_classes = [IsFieldStaff]

    @transaction.atomic
    def post(self, request, wave_id):
        # Wave 조회
        try:
            wave = Wave.objects.select_for_update().get(wave_id=wave_id)
        except Wave.DoesNotExist:
            return Response(
                {'error': '웨이브를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if wave.status not in ('CREATED', 'PICKING'):
            return _pick_error(
                'ALREADY_COMPLETED',
                '이미 피킹이 완료된 웨이브입니다.',
            )

        # 입력 검증
        serializer = PickScanSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data

        # 1. from_location 검증
        from_location = Location.objects.filter(
            barcode=data['from_location_code'].upper(),
        ).first()
        if not from_location or from_location.zone_type not in ('STORAGE', 'PICKING'):
            return _pick_error(
                'WRONG_LOCATION',
                f"유효하지 않은 보관 로케이션입니다: {data['from_location_code']}",
            )

        # 2. product 검증
        product = _resolve_product_by_barcode(data['product_barcode'])
        if not product:
            return _pick_error(
                'WRONG_PRODUCT',
                f"상품을 찾을 수 없습니다: {data['product_barcode']}",
            )

        # 3. to_location 검증 (웨이브 출고존 매칭)
        to_location = Location.objects.filter(
            barcode=data['to_location_code'].upper(),
        ).first()
        if not to_location:
            return _pick_error(
                'WRONG_OUTBOUND_ZONE',
                f"로케이션을 찾을 수 없습니다: {data['to_location_code']}",
            )
        if wave.outbound_zone and to_location != wave.outbound_zone:
            return _pick_error(
                'WRONG_OUTBOUND_ZONE',
                f"웨이브의 출고존이 아닙니다. "
                f"{wave.outbound_zone.barcode}을 스캔해주세요.",
            )

        # 4. 매칭 TotalPickListDetail 조회
        detail = (
            TotalPickListDetail.objects
            .select_for_update()
            .filter(
                pick_list__wave=wave,
                pick_list__product=product,
                from_location=from_location,
            )
            .first()
        )
        if not detail:
            # 올바른 로케이션 추천
            valid_details = (
                TotalPickListDetail.objects
                .filter(
                    pick_list__wave=wave,
                    pick_list__product=product,
                    picked_qty__lt=models_F('qty'),
                )
                .select_related('from_location')
            )
            hint_locations = [
                d.from_location.barcode for d in valid_details[:3]
            ]
            hint = ', '.join(hint_locations) if hint_locations else '없음'
            return _pick_error(
                'WRONG_LOCATION',
                f"해당 로케이션은 이 피킹리스트에 없습니다. "
                f"{hint}을 스캔해주세요.",
            )

        # 5. 수량 검증
        remaining = detail.qty - detail.picked_qty
        if remaining <= 0:
            return _pick_error(
                'ALREADY_COMPLETED',
                '이미 피킹이 완료된 항목입니다.',
            )
        qty = data['qty']
        if qty > remaining:
            return _pick_error(
                'QTY_EXCEEDED',
                f"남은 수량({remaining})을 초과했습니다.",
            )

        # 6. InventoryService.move_stock() 호출
        # 재고 밸런스에서 client 식별
        balance = (
            InventoryBalance.objects
            .filter(product=product, location=from_location, on_hand_qty__gt=0)
            .first()
        )
        if balance:
            try:
                InventoryService.move_stock(
                    product=product,
                    from_location=from_location,
                    to_location=to_location,
                    client=balance.client,
                    qty=qty,
                    reference_id=wave.wave_id,
                    performed_by=request.user,
                    transaction_type='WV_MV',
                    reference_type='WAVE',
                )
            except InsufficientStockError:
                return _pick_error(
                    'QTY_EXCEEDED',
                    '해당 로케이션에 충분한 재고가 없습니다.',
                )

        # 7. Detail 업데이트
        detail.picked_qty += qty
        detail.picked_by = request.user
        detail.picked_at = timezone.now()
        detail.save(update_fields=['picked_qty', 'picked_by', 'picked_at'])

        # 8. TotalPickList 업데이트
        pick_list = detail.pick_list
        total_picked = sum(
            d.picked_qty for d in pick_list.details.all()
        )
        pick_list.picked_qty = total_picked
        if total_picked >= pick_list.total_qty:
            pick_list.status = 'COMPLETED'
        elif total_picked > 0:
            pick_list.status = 'IN_PROGRESS'
        pick_list.save(update_fields=['picked_qty', 'status'])

        # 9. Wave 상태 업데이트
        if wave.status == 'CREATED':
            wave.status = 'PICKING'

        completed_count = wave.pick_lists.filter(status='COMPLETED').count()
        wave.picked_count = completed_count

        # 전체 피킹 완료 → DISTRIBUTING
        all_completed = not wave.pick_lists.exclude(status='COMPLETED').exists()
        if all_completed:
            wave.status = 'DISTRIBUTING'

        wave.save(update_fields=['status', 'picked_count'])

        return Response({
            'success': True,
            'wave_status': wave.status,
            'pick_list_status': pick_list.status,
            'detail_picked_qty': detail.picked_qty,
            'detail_remaining': detail.qty - detail.picked_qty,
            'all_completed': all_completed,
        })


# ------------------------------------------------------------------
# PDA 검수
# ------------------------------------------------------------------

class InspectionListView(APIView):
    """GET /api/v1/waves/{wave_id}/inspection/

    검수 대기 주문 목록을 반환합니다.
    피킹 완료(DISTRIBUTING) 이후, ALLOCATED/PICKING 상태의 주문을 포함합니다.
    """

    permission_classes = [IsFieldStaff]

    def get(self, request, wave_id):
        try:
            wave = Wave.objects.get(wave_id=wave_id)
        except Wave.DoesNotExist:
            return Response(
                {'detail': '웨이브를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        orders = wave.orders.filter(
            status__in=['ALLOCATED', 'PICKING'],
        ).select_related('client').prefetch_related('items')

        serializer = InspectionOrderSerializer(orders, many=True)
        return Response({
            'wave_id': wave.wave_id,
            'wave_status': wave.status,
            'orders': serializer.data,
        })


class InspectionDetailView(APIView):
    """GET /api/v1/waves/orders/{wms_order_id}/inspection-detail/

    검수할 주문의 품목 상세 정보를 반환합니다.
    """

    permission_classes = [IsFieldStaff]

    def get(self, request, wms_order_id):
        try:
            order = OutboundOrder.objects.select_related(
                'client',
            ).prefetch_related(
                'items__product',
            ).get(wms_order_id=wms_order_id)
        except OutboundOrder.DoesNotExist:
            return Response(
                {'detail': '주문을 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not order.wave:
            return Response(
                {'error_code': 'ORDER_NOT_IN_WAVE',
                 'detail': '웨이브에 배정되지 않은 주문입니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        items = InspectionItemSerializer(order.items.all(), many=True)
        return Response({
            'wms_order_id': order.wms_order_id,
            'status': order.status,
            'recipient_name': order.recipient_name,
            'client_name': order.client.company_name,
            'items': items.data,
        })


class InspectScanView(APIView):
    """POST /api/v1/waves/orders/{wms_order_id}/inspect-scan/

    바코드 스캔으로 검수를 수행합니다.
    스캔 1회 = 수량 1개. 동일 상품 3개면 3번 스캔해야 합니다.

    에러코드:
      - ORDER_NOT_IN_WAVE: 웨이브 미배정 주문
      - WRONG_PRODUCT: 주문에 없는 상품
      - ALREADY_COMPLETE: 이미 검수 완료된 주문
      - QTY_EXCEEDED: 해당 상품의 검수수량이 주문수량을 초과
    """

    permission_classes = [IsFieldStaff]

    @transaction.atomic
    def post(self, request, wms_order_id):
        serializer = InspectScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product_barcode = serializer.validated_data['product_barcode']

        # 1. 주문 조회
        try:
            order = OutboundOrder.objects.select_for_update().get(
                wms_order_id=wms_order_id,
            )
        except OutboundOrder.DoesNotExist:
            return Response(
                {'detail': '주문을 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 2. 웨이브 배정 확인
        if not order.wave:
            return Response(
                {'error_code': 'ORDER_NOT_IN_WAVE',
                 'detail': '웨이브에 배정되지 않은 주문입니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3. 이미 검수 완료 확인
        if order.status == 'INSPECTED':
            return Response(
                {'error_code': 'ALREADY_COMPLETE',
                 'detail': '이미 검수 완료된 주문입니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4. 바코드로 상품 조회
        product = _resolve_product_by_barcode(product_barcode)
        if not product:
            return Response(
                {'error_code': 'WRONG_PRODUCT',
                 'detail': f'바코드 {product_barcode}에 해당하는 상품이 없습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 5. 주문 품목에서 해당 상품 찾기
        item = order.items.filter(product=product).first()
        if not item:
            return Response(
                {'error_code': 'WRONG_PRODUCT',
                 'detail': f'이 주문에 {product.name} 상품이 포함되어 있지 않습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 6. 수량 초과 확인
        if item.inspected_qty >= item.qty:
            return Response(
                {'error_code': 'QTY_EXCEEDED',
                 'detail': f'{product.name}: 검수수량({item.inspected_qty})이 '
                           f'주문수량({item.qty})에 도달했습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 7. 검수수량 +1
        item.inspected_qty += 1
        item.save(update_fields=['inspected_qty'])

        # 8. 주문 전체 검수 완료 확인
        all_inspected = True
        for oi in order.items.all():
            if oi.inspected_qty < oi.qty:
                all_inspected = False
                break

        order_completed = False
        if all_inspected:
            order.status = 'INSPECTED'
            order.save(update_fields=['status'])
            order_completed = True

            # Wave inspected_count 증가
            wave = Wave.objects.select_for_update().get(pk=order.wave_id)
            wave.inspected_count += 1
            wave.save(update_fields=['inspected_count'])

            # 시그널 발행 (송장 출력 트리거)
            order_inspected.send(
                sender=OutboundOrder,
                order=order,
                user=request.user,
            )

        return Response({
            'success': True,
            'product_name': product.name,
            'product_barcode': product.barcode,
            'inspected_qty': item.inspected_qty,
            'remaining': item.qty - item.inspected_qty,
            'order_completed': order_completed,
        })


# ------------------------------------------------------------------
# 출고 확정
# ------------------------------------------------------------------

class ShipConfirmView(APIView):
    """출고 확정 API

    POST /api/v1/waves/orders/{wms_order_id}/ship/
    INSPECTED 상태의 주문을 출고 확정합니다.
    """

    permission_classes = [IsFieldStaff]

    def post(self, request, wms_order_id):
        serializer = ShipConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            order = OutboundOrder.objects.select_related(
                'wave', 'client', 'brand',
            ).get(wms_order_id=wms_order_id)
        except OutboundOrder.DoesNotExist:
            return Response(
                {'detail': '주문을 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            ShipmentService.confirm_shipment(
                order=order,
                tracking_number=serializer.validated_data.get('tracking_number'),
                performed_by=request.user,
            )
        except ValueError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except InsufficientStockError as e:
            return Response(
                {'detail': f'출고존 재고 부족: {e}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.refresh_from_db()
        return Response({
            'success': True,
            'wms_order_id': order.wms_order_id,
            'status': order.status,
            'tracking_number': order.tracking_number,
            'shipped_at': order.shipped_at,
        })


class BulkShipView(APIView):
    """일괄 출고 확정 API

    POST /api/v1/waves/{wave_id}/bulk-ship/
    해당 웨이브의 INSPECTED 상태 주문 전체 출고 확정.
    """

    permission_classes = [IsOfficeStaff]

    def post(self, request, wave_id):
        try:
            wave = Wave.objects.get(wave_id=wave_id)
        except Wave.DoesNotExist:
            return Response(
                {'detail': '웨이브를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        orders = wave.orders.filter(
            status='INSPECTED',
        ).select_related('client', 'brand')

        if not orders.exists():
            return Response(
                {'detail': 'INSPECTED 상태의 주문이 없습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        shipped = []
        errors = []
        for order in orders:
            try:
                ShipmentService.confirm_shipment(
                    order=order,
                    performed_by=request.user,
                )
                shipped.append(order.wms_order_id)
            except (ValueError, InsufficientStockError) as e:
                errors.append({
                    'wms_order_id': order.wms_order_id,
                    'error': str(e),
                })

        wave.refresh_from_db()
        return Response({
            'success': True,
            'wave_id': wave.wave_id,
            'wave_status': wave.status,
            'shipped_count': len(shipped),
            'shipped_orders': shipped,
            'errors': errors,
        })
