"""
반품 관리 뷰
"""
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.inventory.models import Product, ProductBarcode, Location
from apps.waves.permissions import IsFieldStaff

from .models import ReturnOrder
from .serializers import (
    ReturnOrderListSerializer,
    ReturnOrderDetailSerializer,
    ReturnOrderCreateSerializer,
    ReturnOrderItemSerializer,
)
from .services import ReturnInspectionService


def _resolve_product(barcode):
    """바코드로 Product 조회 (ProductBarcode 우선, Product.barcode 폴백)"""
    pb = ProductBarcode.objects.select_related('product').filter(barcode=barcode).first()
    if pb:
        return pb.product
    return Product.objects.filter(barcode=barcode).first()


class ReturnOrderViewSet(viewsets.ModelViewSet):
    """반품주문 CRUD

    필터: client_id, status, return_reason, date_from, date_to
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ReturnOrder.objects.select_related(
            'client', 'brand', 'created_by', 'original_order',
        ).prefetch_related('items__product')

        params = self.request.query_params

        client_id = params.get('client_id')
        if client_id:
            qs = qs.filter(client_id=client_id)

        status_filter = params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        reason = params.get('return_reason')
        if reason:
            qs = qs.filter(return_reason=reason)

        date_from = params.get('date_from')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        date_to = params.get('date_to')
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return ReturnOrderListSerializer
        if self.action == 'create':
            return ReturnOrderCreateSerializer
        return ReturnOrderDetailSerializer

    def perform_create(self, serializer):
        return serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = self.perform_create(serializer)
        out = ReturnOrderDetailSerializer(order)
        return Response(out.data, status=status.HTTP_201_CREATED)


class PDAReturnInspectView(APIView):
    """PDA 반품 검수

    POST /api/v1/returns/{return_id}/inspect/
    {
        "product_barcode": "...",
        "good_qty": 9,
        "defect_qty": 1,
        "disposition": "RESTOCK"
    }
    """

    permission_classes = [IsFieldStaff]

    def post(self, request, return_id):
        # 반품주문 조회
        try:
            order = ReturnOrder.objects.select_related('client', 'brand').get(
                return_id=return_id,
            )
        except ReturnOrder.DoesNotExist:
            return Response(
                {'error': f'반품번호 {return_id}을(를) 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 상태 검증
        if order.status not in ('RECEIVED', 'INSPECTING'):
            return Response(
                {'error': f'현재 상태({order.get_status_display()})에서는 검수할 수 없습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 파라미터 파싱
        barcode = request.data.get('product_barcode', '').strip()
        good_qty = request.data.get('good_qty')
        defect_qty = request.data.get('defect_qty', 0)
        disposition = request.data.get('disposition', '').strip()

        if not barcode or good_qty is None or not disposition:
            return Response(
                {'error': 'product_barcode, good_qty, disposition은 필수입니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            good_qty = int(good_qty)
            defect_qty = int(defect_qty)
        except (ValueError, TypeError):
            return Response(
                {'error': '수량은 정수여야 합니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if disposition not in ('RESTOCK', 'DEFECT_ZONE', 'DISPOSE'):
            return Response(
                {'error': f'유효하지 않은 disposition: {disposition}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 바코드 → 상품
        product = _resolve_product(barcode)
        if not product:
            return Response(
                {'error': f'바코드 {barcode}에 해당하는 상품을 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 반품 품목 매칭
        item = order.items.filter(product=product).first()
        if not item:
            return Response(
                {'error': f'반품주문에 해당 상품({product.name})이 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 반품존 조회
        return_location = Location.objects.filter(
            zone_type='RETURN', is_active=True,
        ).first()
        if not return_location:
            return Response(
                {'error': '반품존(RETURN) 로케이션이 설정되어 있지 않습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 검수 처리
        item, order_status, all_inspected = ReturnInspectionService.inspect_item(
            return_order=order,
            item=item,
            good_qty=good_qty,
            defect_qty=defect_qty,
            disposition=disposition,
            location=return_location,
            performed_by=request.user,
        )

        return Response({
            'success': True,
            'item': ReturnOrderItemSerializer(item).data,
            'order_status': order_status,
            'order_status_display': order.get_status_display(),
            'all_inspected': all_inspected,
        })
