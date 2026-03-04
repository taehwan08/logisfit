"""
입고 관리 뷰
"""
import logging

from django.db import transaction
from django.db.models import Q, Sum
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import InboundOrder, InboundOrderItem
from .permissions import IsFieldStaff
from .serializers import (
    InboundOrderListSerializer,
    InboundOrderDetailSerializer,
    InboundOrderCreateSerializer,
    InboundOrderUpdateSerializer,
    InboundOrderItemSerializer,
)
from .slack import send_inbound_order_notification_async
from apps.inventory.models import Product, ProductBarcode, Location, InventoryBalance
from apps.inventory.services import InventoryService

logger = logging.getLogger(__name__)


class InboundOrderViewSet(viewsets.ModelViewSet):
    """입고예정 ViewSet

    목록/상세/생성/수정 + 상태 변경 액션 + 엑셀 업로드
    필터: client_id, status, date_from, date_to
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = InboundOrder.objects.select_related(
            'client', 'brand', 'created_by',
        ).prefetch_related('items__product', 'items__putaway_location')

        params = self.request.query_params

        client_id = params.get('client_id')
        if client_id:
            qs = qs.filter(client_id=client_id)

        status_filter = params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        date_from = params.get('date_from')
        if date_from:
            qs = qs.filter(expected_date__gte=date_from)

        date_to = params.get('date_to')
        if date_to:
            qs = qs.filter(expected_date__lte=date_to)

        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return InboundOrderListSerializer
        if self.action == 'create':
            return InboundOrderCreateSerializer
        if self.action in ('update', 'partial_update'):
            return InboundOrderUpdateSerializer
        return InboundOrderDetailSerializer

    def perform_create(self, serializer):
        order = serializer.save(created_by=self.request.user)
        send_inbound_order_notification_async(order)
        return order

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = self.perform_create(serializer)
        out = InboundOrderDetailSerializer(order)
        return Response(out.data, status=status.HTTP_201_CREATED)

    # ------------------------------------------------------------------
    # 상태 변경 액션
    # ------------------------------------------------------------------
    def _transition(self, request, pk, target_status):
        """상태 전이 공통 로직"""
        order = self.get_object()
        expected = InboundOrder.STATUS_TRANSITIONS.get(order.status)

        if expected != target_status:
            return Response(
                {'error': f'현재 상태({order.get_status_display()})에서 '
                          f'{dict(InboundOrder.STATUS_CHOICES).get(target_status)} 전이 불가'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = target_status
        order.save(update_fields=['status', 'updated_at'])
        return Response(InboundOrderDetailSerializer(order).data)

    @action(detail=True, methods=['post'])
    def arrive(self, request, pk=None):
        """도착 처리: PLANNED → ARRIVED"""
        return self._transition(request, pk, 'ARRIVED')

    @action(detail=True, methods=['post'])
    def start_inspect(self, request, pk=None):
        """검수 시작: ARRIVED → INSPECTING"""
        return self._transition(request, pk, 'INSPECTING')

    @action(detail=True, methods=['post'])
    def complete_inspect(self, request, pk=None):
        """검수 완료: INSPECTING → INSPECTED

        Body (optional): items 배열로 검수수량/불량수량 일괄 업데이트
        [{"item_id": 1, "inspected_qty": 100, "defect_qty": 2}, ...]
        """
        order = self.get_object()
        expected = InboundOrder.STATUS_TRANSITIONS.get(order.status)
        if expected != 'INSPECTED':
            return Response(
                {'error': f'현재 상태({order.get_status_display()})에서 검수완료 전이 불가'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 검수 수량 업데이트
        items_data = request.data.get('items', [])
        if items_data:
            item_map = {item.pk: item for item in order.items.all()}
            for entry in items_data:
                item = item_map.get(entry.get('item_id'))
                if item:
                    if 'inspected_qty' in entry:
                        item.inspected_qty = int(entry['inspected_qty'])
                    if 'defect_qty' in entry:
                        item.defect_qty = int(entry['defect_qty'])
                    item.save(update_fields=['inspected_qty', 'defect_qty'])

        order.status = 'INSPECTED'
        order.save(update_fields=['status', 'updated_at'])
        return Response(InboundOrderDetailSerializer(order).data)

    @action(detail=True, methods=['post'])
    def complete_putaway(self, request, pk=None):
        """적치 완료: INSPECTED → PUTAWAY_COMPLETE

        각 품목의 검수수량(양품)을 InventoryBalance에 입고 처리합니다.
        Body (optional): items 배열로 적치 로케이션 지정
        [{"item_id": 1, "putaway_location_id": 5}, ...]
        """
        order = self.get_object()
        expected = InboundOrder.STATUS_TRANSITIONS.get(order.status)
        if expected != 'PUTAWAY_COMPLETE':
            return Response(
                {'error': f'현재 상태({order.get_status_display()})에서 적치완료 전이 불가'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 적치 로케이션 업데이트
        items_data = request.data.get('items', [])
        if items_data:
            item_map = {item.pk: item for item in order.items.select_related('putaway_location').all()}
            for entry in items_data:
                item = item_map.get(entry.get('item_id'))
                if item and entry.get('putaway_location_id'):
                    item.putaway_location_id = int(entry['putaway_location_id'])
                    item.save(update_fields=['putaway_location_id'])

        # 재고 입고 처리
        with transaction.atomic():
            for item in order.items.select_related('product', 'putaway_location').all():
                good_qty = item.inspected_qty - item.defect_qty
                if good_qty <= 0 or not item.putaway_location:
                    continue

                InventoryService.receive_stock(
                    product=item.product,
                    location=item.putaway_location,
                    client=order.client,
                    qty=good_qty,
                    lot_number=item.lot_number,
                    expiry_date=item.expiry_date,
                    reference_id=order.inbound_id,
                    performed_by=request.user,
                    brand=order.brand,
                )

            order.status = 'PUTAWAY_COMPLETE'
            order.save(update_fields=['status', 'updated_at'])

        return Response(InboundOrderDetailSerializer(order).data)

    # ------------------------------------------------------------------
    # 엑셀 업로드
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser])
    def upload_excel(self, request, pk=None):
        """입고 품목 엑셀 업로드

        표준 양식: 바코드 | 상품명 | 예정수량 | 로트번호 | 유통기한
        """
        order = self.get_object()
        file = request.FILES.get('file')
        if not file:
            return Response(
                {'error': '파일을 첨부해주세요.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            import openpyxl
        except ImportError:
            return Response(
                {'error': 'openpyxl이 설치되지 않았습니다.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
            ws = wb.active

            from apps.inventory.models import Product

            created = 0
            errors = []
            for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                if not row or not row[0]:
                    continue

                barcode = str(row[0]).strip()
                expected_qty = row[2] if len(row) > 2 else None
                lot_number = str(row[3]).strip() if len(row) > 3 and row[3] else ''
                expiry_date = None
                if len(row) > 4 and row[4]:
                    from django.utils.dateparse import parse_date
                    expiry_date = parse_date(str(row[4]).strip())

                if not expected_qty:
                    errors.append(f'{row_idx}행: 예정수량 누락')
                    continue

                product = Product.objects.filter(barcode=barcode).first()
                if not product:
                    errors.append(f'{row_idx}행: 상품 미등록 ({barcode})')
                    continue

                try:
                    InboundOrderItem.objects.create(
                        inbound_order=order,
                        product=product,
                        expected_qty=int(expected_qty),
                        lot_number=lot_number,
                        expiry_date=expiry_date,
                    )
                    created += 1
                except Exception as e:
                    errors.append(f'{row_idx}행: {str(e)}')

            wb.close()

            return Response({
                'success': True,
                'created': created,
                'errors': errors[:20],
            })

        except Exception as e:
            logger.error('입고 엑셀 업로드 실패: %s', e, exc_info=True)
            return Response(
                {'error': f'파일 처리 중 오류: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ============================================================================
# PDA 전용 API
# ============================================================================

def _resolve_product_by_barcode(barcode):
    """바코드로 Product 조회 (ProductBarcode 테이블 우선, Product.barcode 폴백)"""
    pb = ProductBarcode.objects.select_related('product').filter(barcode=barcode).first()
    if pb:
        return pb.product
    return Product.objects.filter(barcode=barcode).first()


class PDAInspectView(APIView):
    """PDA 검수 API

    POST /api/v1/inbound/{inbound_id}/inspect/
    {
        "product_barcode": "8801234567890",
        "qty": 10,
        "defect_qty": 1,
        "notes": ""
    }
    """
    permission_classes = [IsFieldStaff]

    def post(self, request, inbound_id):
        try:
            order = InboundOrder.objects.select_related('client').get(
                inbound_id=inbound_id,
            )
        except InboundOrder.DoesNotExist:
            return Response(
                {'error': f'입고번호 {inbound_id}을(를) 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 상태 체크: ARRIVED 또는 INSPECTING만 검수 가능
        if order.status not in ('ARRIVED', 'INSPECTING'):
            return Response(
                {'error': f'현재 상태({order.get_status_display()})에서는 검수할 수 없습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        barcode = request.data.get('product_barcode', '').strip()
        qty = request.data.get('qty')
        defect_qty = request.data.get('defect_qty', 0)

        if not barcode or qty is None:
            return Response(
                {'error': 'product_barcode, qty는 필수입니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            qty = int(qty)
            defect_qty = int(defect_qty)
        except (ValueError, TypeError):
            return Response(
                {'error': '수량은 정수여야 합니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 바코드로 상품 조회
        product = _resolve_product_by_barcode(barcode)
        if not product:
            return Response(
                {'error': f'바코드 {barcode}에 해당하는 상품을 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # InboundOrderItem 매칭
        item = order.items.filter(product=product).first()
        if not item:
            return Response(
                {'error': f'입고예정에 해당 상품({product.name})이 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 검수 수량 누적
        item.inspected_qty += qty
        item.defect_qty += defect_qty
        item.save(update_fields=['inspected_qty', 'defect_qty'])

        # 첫 검수 시 ARRIVED → INSPECTING
        if order.status == 'ARRIVED':
            order.status = 'INSPECTING'
            order.save(update_fields=['status', 'updated_at'])

        # 모든 아이템 검수 완료 체크
        all_inspected = all(
            i.inspected_qty >= i.expected_qty
            for i in order.items.all()
        )
        if all_inspected and order.status == 'INSPECTING':
            order.status = 'INSPECTED'
            order.save(update_fields=['status', 'updated_at'])

        order.refresh_from_db()

        return Response({
            'success': True,
            'item': InboundOrderItemSerializer(item).data,
            'order_status': order.status,
            'order_status_display': order.get_status_display(),
            'all_inspected': all_inspected,
        })


class PDAPutawayView(APIView):
    """PDA 적치 API

    POST /api/v1/inbound/{inbound_id}/putaway/
    {
        "product_barcode": "8801234567890",
        "location_code": "B9-A-03-02-01",
        "qty": 9
    }
    """
    permission_classes = [IsFieldStaff]

    def post(self, request, inbound_id):
        try:
            order = InboundOrder.objects.select_related('client', 'brand').get(
                inbound_id=inbound_id,
            )
        except InboundOrder.DoesNotExist:
            return Response(
                {'error': f'입고번호 {inbound_id}을(를) 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 상태 체크: INSPECTED 또는 이미 PUTAWAY 진행중
        if order.status not in ('INSPECTED', 'PUTAWAY_COMPLETE'):
            return Response(
                {'error': f'현재 상태({order.get_status_display()})에서는 적치할 수 없습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        barcode = request.data.get('product_barcode', '').strip()
        location_code = request.data.get('location_code', '').strip()
        qty = request.data.get('qty')

        if not barcode or not location_code or qty is None:
            return Response(
                {'error': 'product_barcode, location_code, qty는 필수입니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            qty = int(qty)
            if qty < 1:
                raise ValueError
        except (ValueError, TypeError):
            return Response(
                {'error': '수량은 1 이상 정수여야 합니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 바코드로 상품 조회
        product = _resolve_product_by_barcode(barcode)
        if not product:
            return Response(
                {'error': f'바코드 {barcode}에 해당하는 상품을 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 로케이션 조회
        try:
            location = Location.objects.get(barcode=location_code.upper())
        except Location.DoesNotExist:
            return Response(
                {'error': f'로케이션 {location_code}을(를) 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # InboundOrderItem 매칭
        item = order.items.filter(product=product).first()
        if not item:
            return Response(
                {'error': f'입고예정에 해당 상품({product.name})이 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 재고 입고 + 히스토리
        with transaction.atomic():
            InventoryService.receive_stock(
                product=product,
                location=location,
                client=order.client,
                qty=qty,
                lot_number=item.lot_number,
                expiry_date=item.expiry_date,
                reference_id=order.inbound_id,
                performed_by=request.user,
                brand=order.brand,
            )

            # 적치 로케이션 기록
            item.putaway_location = location
            item.save(update_fields=['putaway_location_id'])

        # 모든 아이템 적치 완료 체크
        all_putaway = all(
            i.putaway_location_id is not None
            for i in order.items.all()
        )
        if all_putaway and order.status == 'INSPECTED':
            order.status = 'PUTAWAY_COMPLETE'
            order.save(update_fields=['status', 'updated_at'])

        order.refresh_from_db()

        return Response({
            'success': True,
            'item': InboundOrderItemSerializer(item).data,
            'order_status': order.status,
            'order_status_display': order.get_status_display(),
            'all_putaway': all_putaway,
        })


class SuggestLocationView(APIView):
    """로케이션 추천 API

    GET /api/v1/inbound/suggest-location/?product_id=123

    동일 SKU가 이미 있는 STORAGE/PICKING 로케이션을 반환합니다.
    없으면 빈 STORAGE 로케이션을 반환합니다.
    """
    permission_classes = [IsFieldStaff]

    def get(self, request):
        product_id = request.query_params.get('product_id')
        if not product_id:
            return Response(
                {'error': 'product_id는 필수입니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1) 동일 SKU가 이미 있는 STORAGE/PICKING 로케이션
        existing = (
            InventoryBalance.objects
            .filter(
                product_id=product_id,
                on_hand_qty__gt=0,
                location__zone_type__in=['STORAGE', 'PICKING'],
                location__is_active=True,
            )
            .select_related('location')
            .order_by('-on_hand_qty')
        )

        existing_locations = [
            {
                'location_id': b.location_id,
                'location_code': b.location.barcode,
                'zone_type': b.location.zone_type,
                'current_qty': b.on_hand_qty,
                'reason': 'same_sku',
            }
            for b in existing[:5]
        ]

        if existing_locations:
            return Response({
                'suggestions': existing_locations,
                'reason': '동일 상품 보관중인 로케이션',
            })

        # 2) 빈 STORAGE 로케이션 (재고 없는 활성 로케이션)
        occupied_location_ids = (
            InventoryBalance.objects
            .filter(on_hand_qty__gt=0)
            .values_list('location_id', flat=True)
        )

        empty_storage = (
            Location.objects
            .filter(
                zone_type='STORAGE',
                is_active=True,
            )
            .exclude(pk__in=occupied_location_ids)
            .order_by('barcode')[:5]
        )

        empty_locations = [
            {
                'location_id': loc.pk,
                'location_code': loc.barcode,
                'zone_type': loc.zone_type,
                'current_qty': 0,
                'reason': 'empty',
            }
            for loc in empty_storage
        ]

        return Response({
            'suggestions': empty_locations,
            'reason': '빈 보관 로케이션' if empty_locations else '추천 로케이션 없음',
        })
