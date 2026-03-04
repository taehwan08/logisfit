"""
이력 관리 뷰
"""
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import InventoryTransaction
from .serializers import InventoryTransactionSerializer


class InventoryTransactionListView(generics.ListAPIView):
    """재고 트랜잭션 목록 조회 (읽기 전용)

    GET /api/v1/history/transactions/
    쿼리 파라미터:
        - client_id: 거래처 ID
        - product_id: 상품 ID
        - type: 트랜잭션 유형 (GR, GI, MV, ...)
        - reference_type: 참조 유형 (INBOUND, OUTBOUND, ...)
        - date_from: 시작일 (YYYY-MM-DD)
        - date_to: 종료일 (YYYY-MM-DD)
    """

    serializer_class = InventoryTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = InventoryTransaction.objects.select_related(
            'client', 'brand', 'product',
            'from_location', 'to_location', 'performed_by',
        )

        params = self.request.query_params

        client_id = params.get('client_id')
        if client_id:
            qs = qs.filter(client_id=client_id)

        product_id = params.get('product_id')
        if product_id:
            qs = qs.filter(product_id=product_id)

        txn_type = params.get('type')
        if txn_type:
            qs = qs.filter(transaction_type=txn_type)

        ref_type = params.get('reference_type')
        if ref_type:
            qs = qs.filter(reference_type=ref_type)

        date_from = params.get('date_from')
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)

        date_to = params.get('date_to')
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)

        return qs
