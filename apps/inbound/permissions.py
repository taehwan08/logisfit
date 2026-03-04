"""
입고 관리 퍼미션
"""
from rest_framework.permissions import IsAuthenticated


class IsFieldStaff(IsAuthenticated):
    """현장 작업 가능 역할 퍼미션

    ADMIN, OFFICE, FIELD 역할만 접근 허용.
    """

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        user = request.user
        return user.is_admin or user.is_office or user.is_field or user.is_superuser
