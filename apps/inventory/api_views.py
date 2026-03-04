"""
재고 외부 제공 API 뷰
"""
from django.db.models import Sum, F

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination

from .models import InventoryBalance, SafetyStock, Product
from .serializers import InventoryDetailSerializer, InventoryBulkSerializer
from .permissions import InventoryAPIPermission


def _build_product_inventory(product_rows, safety_map, include_locations=True):
    """상품별 재고 집계 데이터 빌드

    Args:
        product_rows: InventoryBalance queryset (상품 기준 집계 또는 raw)
        safety_map: {product_id: min_qty} 안전재고 매핑
        include_locations: 로케이션 상세 포함 여부
    """
    results = []
    for row in product_rows:
        pid = row['product_id']
        on_hand = row['on_hand'] or 0
        allocated = row['allocated'] or 0
        reserved = row['reserved'] or 0
        available = on_hand - allocated - reserved
        ss = safety_map.get(pid)

        item = {
            'sku': row['product__barcode'],
            'product_name': row['product__name'],
            'client_id': row['client_id'],
            'brand_id': row.get('product__brand_id'),
            'on_hand': on_hand,
            'allocated': allocated,
            'reserved': reserved,
            'available': available,
            'safety_stock': ss,
            'is_below_safety': on_hand < ss if ss is not None else False,
        }
        if include_locations and 'locations' in row:
            item['locations'] = row['locations']
        results.append(item)
    return results


class InventoryDetailView(APIView):
    """상품별 5단 재고 집계 + 로케이션별 상세

    GET /api/v1/inventory/?client_id=&product_id=&sku=&brand_id=&location_id=
    """
    permission_classes = [InventoryAPIPermission]

    def get(self, request):
        client_id = request.query_params.get('client_id')
        if not client_id:
            return Response(
                {'error': 'client_id는 필수입니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 밸런스 쿼리
        qs = InventoryBalance.objects.filter(client_id=client_id)

        product_id = request.query_params.get('product_id')
        if product_id:
            qs = qs.filter(product_id=product_id)

        sku = request.query_params.get('sku')
        if sku:
            qs = qs.filter(product__barcode=sku)

        brand_id = request.query_params.get('brand_id')
        if brand_id:
            qs = qs.filter(product__brand_id=brand_id)

        location_id = request.query_params.get('location_id')
        if location_id:
            qs = qs.filter(location_id=location_id)

        # 로케이션 상세를 위해 개별 밸런스 로우를 가져옴
        balances = qs.select_related('product', 'location').values(
            'product_id', 'product__barcode', 'product__name',
            'product__brand_id', 'client_id',
            'location__barcode', 'location__zone_type',
            'on_hand_qty', 'allocated_qty', 'reserved_qty',
        )

        # 상품별 집계
        product_map = {}
        product_ids = set()
        for b in balances:
            pid = b['product_id']
            product_ids.add(pid)
            if pid not in product_map:
                product_map[pid] = {
                    'product_id': pid,
                    'product__barcode': b['product__barcode'],
                    'product__name': b['product__name'],
                    'product__brand_id': b['product__brand_id'],
                    'client_id': b['client_id'],
                    'on_hand': 0,
                    'allocated': 0,
                    'reserved': 0,
                    'locations': [],
                }
            entry = product_map[pid]
            entry['on_hand'] += b['on_hand_qty'] or 0
            entry['allocated'] += b['allocated_qty'] or 0
            entry['reserved'] += b['reserved_qty'] or 0
            entry['locations'].append({
                'location_code': b['location__barcode'],
                'zone_type': b['location__zone_type'],
                'qty': b['on_hand_qty'] or 0,
            })

        # 안전재고 매핑
        safety_map = dict(
            SafetyStock.objects.filter(
                client_id=client_id, product_id__in=product_ids,
            ).values_list('product_id', 'min_qty')
        )

        results = _build_product_inventory(
            product_map.values(), safety_map, include_locations=True,
        )

        serializer = InventoryDetailSerializer(results, many=True)
        return Response({'results': serializer.data})


class InventoryBulkView(ListAPIView):
    """화주사 전체 상품 재고 요약 (로케이션 상세 제외, 페이지네이션)

    GET /api/v1/inventory/bulk/?client_id=
    """
    permission_classes = [InventoryAPIPermission]
    serializer_class = InventoryBulkSerializer

    def get_queryset(self):
        # ListAPIView에서 사용하지 않음 (list 오버라이드)
        return InventoryBalance.objects.none()

    def list(self, request, *args, **kwargs):
        client_id = request.query_params.get('client_id')
        if not client_id:
            return Response(
                {'error': 'client_id는 필수입니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 상품별 집계
        rows = (
            InventoryBalance.objects
            .filter(client_id=client_id)
            .values(
                'product_id', 'product__barcode', 'product__name',
                'product__brand_id', 'client_id',
            )
            .annotate(
                on_hand=Sum('on_hand_qty'),
                allocated=Sum('allocated_qty'),
                reserved=Sum('reserved_qty'),
            )
            .order_by('product__name')
        )

        # 페이지네이션
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(list(rows), request, view=self)

        product_ids = [r['product_id'] for r in page]
        safety_map = dict(
            SafetyStock.objects.filter(
                client_id=client_id, product_id__in=product_ids,
            ).values_list('product_id', 'min_qty')
        )

        results = _build_product_inventory(
            page, safety_map, include_locations=False,
        )

        serializer = InventoryBulkSerializer(results, many=True)
        return paginator.get_paginated_response(serializer.data)
