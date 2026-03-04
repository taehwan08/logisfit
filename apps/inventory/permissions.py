"""
재고 API 권한
"""
from rest_framework.permissions import IsAuthenticated


class InventoryAPIPermission(IsAuthenticated):
    """재고 API 퍼미션

    - CLIENT 역할: 자기 소속 거래처(client_id)만 조회 가능
    - 그 외(ADMIN, OFFICE, FIELD 등): 모든 거래처 조회 가능
    """

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        user = request.user
        if not user.is_client:
            return True

        # CLIENT 역할: client_id 파라미터가 자기 소속 거래처인지 확인
        client_id = request.query_params.get('client_id')
        if not client_id:
            return False  # CLIENT 역할은 client_id 필수

        try:
            return user.clients.filter(pk=int(client_id)).exists()
        except (ValueError, TypeError):
            return False
