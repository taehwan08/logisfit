"""
외부 연동 어댑터 뷰
"""
import logging

from django.db import transaction
from django.utils import timezone as tz
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clients.models import Client
from apps.inventory.models import Product
from apps.inventory.services import InventoryService
from apps.inventory.exceptions import InsufficientStockError
from apps.waves.models import OutboundOrder, OutboundOrderItem
from apps.waves.permissions import IsOfficeStaff

from .b2b.excel_parser import B2BExcelParser
from .serializers import B2BUploadSerializer

logger = logging.getLogger(__name__)


class B2BUploadView(APIView):
    """B2B 발주 엑셀 업로드

    POST /api/v1/adapters/b2b/upload/
    Content-Type: multipart/form-data
    """

    permission_classes = [IsOfficeStaff]
    parser_classes = [MultiPartParser]

    def post(self, request):
        serializer = B2BUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        client_id = serializer.validated_data['client_id']
        file = serializer.validated_data['file']

        # 거래처 확인
        try:
            client = Client.objects.get(pk=client_id)
        except Client.DoesNotExist:
            return Response(
                {'error': '거래처를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 엑셀 파싱
        parser = B2BExcelParser()
        try:
            orders_data = parser.parse(file)
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 주문 생성
        created = []
        skipped = []
        errors = []

        for order_data in orders_data:
            source_order_id = order_data['source_order_id']

            # 중복 체크
            if OutboundOrder.objects.filter(
                source='B2B_EXCEL',
                source_order_id=source_order_id,
                client=client,
            ).exists():
                skipped.append(source_order_id)
                continue

            try:
                order = self._create_order(
                    order_data, client, request.user,
                )
                created.append(order.wms_order_id)
            except Exception as e:
                errors.append({
                    'source_order_id': source_order_id,
                    'error': str(e),
                })

        return Response({
            'success': True,
            'total_parsed': len(orders_data),
            'created_count': len(created),
            'created_orders': created,
            'skipped_count': len(skipped),
            'skipped_orders': skipped,
            'error_count': len(errors),
            'errors': errors,
        }, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def _create_order(self, order_data, client, user):
        """표준 포맷 → OutboundOrder 생성 + 재고 할당"""
        items_data = order_data['items']

        # 상품 조회
        resolved_items = []
        for item in items_data:
            product = self._resolve_product(item['sku'])
            if not product:
                raise ValueError(f"상품을 찾을 수 없습니다: {item['sku']}")
            resolved_items.append({
                'product': product,
                'qty': item['qty'],
                'source_item_id': item.get('source_item_id', ''),
            })

        order = OutboundOrder.objects.create(
            source='B2B_EXCEL',
            source_order_id=order_data['source_order_id'],
            client=client,
            order_type='B2B',
            ordered_at=tz.now(),
            recipient_name=order_data.get('recipient_name', ''),
            recipient_phone=order_data.get('recipient_phone', ''),
            recipient_address=order_data.get('recipient_address', ''),
            recipient_zip=order_data.get('recipient_zip', ''),
            shipping_memo=order_data.get('shipping_memo', ''),
        )

        for item in resolved_items:
            OutboundOrderItem.objects.create(
                order=order,
                product=item['product'],
                qty=item['qty'],
                source_item_id=item['source_item_id'],
            )

        # 재고 할당
        hold_reasons = []
        for item in resolved_items:
            try:
                InventoryService.allocate_stock(
                    product=item['product'],
                    client=client,
                    qty=item['qty'],
                    reference_id=order.wms_order_id,
                    performed_by=user,
                )
            except InsufficientStockError as e:
                hold_reasons.append(
                    f"{item['product'].name}: 요청 {e.requested}, 가용 {e.available}"
                )

        if hold_reasons:
            order.status = 'HELD'
            order.hold_reason = '; '.join(hold_reasons)
            order.save(update_fields=['status', 'hold_reason', 'updated_at'])
            for item in resolved_items:
                try:
                    InventoryService.deallocate_stock(
                        product=item['product'],
                        client=client,
                        qty=item['qty'],
                        reference_id=order.wms_order_id,
                        performed_by=user,
                    )
                except InsufficientStockError:
                    pass
        else:
            order.status = 'ALLOCATED'
            order.save(update_fields=['status', 'updated_at'])

        return order

    @staticmethod
    def _resolve_product(sku):
        from apps.inventory.models import ProductBarcode
        product = Product.objects.filter(barcode=sku).first()
        if product:
            return product
        pb = ProductBarcode.objects.select_related('product').filter(
            barcode=sku,
        ).first()
        return pb.product if pb else None
