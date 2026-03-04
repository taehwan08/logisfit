"""
입고 관리 뷰
"""
import logging

from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import InboundOrder, InboundOrderItem
from .serializers import (
    InboundOrderListSerializer,
    InboundOrderDetailSerializer,
    InboundOrderCreateSerializer,
    InboundOrderUpdateSerializer,
    InboundOrderItemSerializer,
)
from .slack import send_inbound_order_notification_async
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
