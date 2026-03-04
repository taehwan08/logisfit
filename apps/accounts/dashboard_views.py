from rest_framework.response import Response
from rest_framework.views import APIView

from apps.waves.permissions import IsFieldStaff, IsOfficeStaff

from .dashboard_services import (
    get_client_dashboard,
    get_field_dashboard,
    get_office_dashboard,
)


class OfficeDashboardView(APIView):
    permission_classes = [IsOfficeStaff]

    def get(self, request):
        data = get_office_dashboard()
        return Response(data)


class FieldDashboardView(APIView):
    permission_classes = [IsFieldStaff]

    def get(self, request):
        data = get_field_dashboard(request.user)
        return Response(data)


class ClientDashboardView(APIView):

    def get(self, request):
        if not request.user.is_client:
            return Response(
                {'detail': '거래처 사용자만 접근할 수 있습니다.'},
                status=403,
            )
        data = get_client_dashboard(request.user)
        return Response(data)
