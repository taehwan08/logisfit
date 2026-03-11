"""
리포트 뷰
"""
import os

from django.http import HttpResponse
from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.views import AdminRequiredMixin
from apps.waves.permissions import IsOfficeStaff

from .daily_parcel import process_daily_parcel_report
from .excel import build_workbook, workbook_to_response
from .models import ReportFile
from .serializers import (
    InventoryLedgerParamSerializer,
    ShipmentSummaryParamSerializer,
    WorkerProductivityParamSerializer,
    SafetyStockAlertParamSerializer,
    ReportFileSerializer,
)
from . import services


# ------------------------------------------------------------------
# 페이지 기반 리포트
# ------------------------------------------------------------------

class DailyParcelReportView(AdminRequiredMixin, View):
    """일일택배사업부 리포트

    사방넷 출고 엑셀 파일 업로드 → 브랜드별 단포/합포 집계 엑셀 다운로드
    """
    template_name = 'reports/daily_parcel_upload.html'

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        uploaded_file = request.FILES.get('excel_file')

        if not uploaded_file:
            return render(request, self.template_name, {
                'error': '파일을 선택해주세요.',
            })

        # 확장자 검증
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in ('.xls', '.xlsx'):
            return render(request, self.template_name, {
                'error': '엑셀 파일(.xls 또는 .xlsx)만 업로드 가능합니다.',
            })

        try:
            output = process_daily_parcel_report(uploaded_file)
            response = HttpResponse(
                output.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            response['Content-Disposition'] = 'attachment; filename="일일택배사업부_결과.xlsx"'
            return response
        except Exception as e:
            return render(request, self.template_name, {
                'error': f'처리 중 오류가 발생했습니다: {str(e)}',
            })

ASYNC_THRESHOLD = 5000


# ------------------------------------------------------------------
# 엑셀 컬럼 정의
# ------------------------------------------------------------------

LEDGER_COLUMNS = [
    ('sku', 'SKU', 18),
    ('product_name', '상품명', 30),
    ('opening_balance', '기초재고', 12),
    ('inbound_qty', '입고', 10),
    ('return_qty', '반품입고', 10),
    ('outbound_qty', '출고', 10),
    ('adjustment_qty', '조정', 10),
    ('movement_qty', '이동', 10),
    ('closing_balance', '기말재고', 12),
]

SHIPMENT_COLUMNS = [
    ('date', '날짜', 14),
    ('client_name', '화주사', 20),
    ('brand_name', '브랜드', 16),
    ('order_count', '출고건수', 12),
    ('total_qty', '출고수량', 12),
]

WORKER_COLUMNS = [
    ('worker_id', 'ID', 8),
    ('worker_name', '작업자', 16),
    ('pick_count', '피킹건수', 12),
    ('pick_qty', '피킹수량', 12),
    ('transaction_count', '처리건수', 12),
]

SAFETY_COLUMNS = [
    ('sku', 'SKU', 18),
    ('product_name', '상품명', 30),
    ('client_name', '화주사', 20),
    ('min_qty', '안전재고', 12),
    ('current_qty', '현재재고', 12),
    ('shortage', '부족수량', 12),
]


# ------------------------------------------------------------------
# 베이스 뷰
# ------------------------------------------------------------------

class BaseReportView(APIView):
    """리포트 베이스 뷰"""

    permission_classes = [IsOfficeStaff]
    param_serializer_class = None
    report_type = ''
    excel_columns = []
    excel_sheet_title = '리포트'
    excel_filename_prefix = 'report'

    def get_data(self, params):
        raise NotImplementedError

    def get(self, request):
        # 1. 파라미터 검증
        ser = self.param_serializer_class(data=request.query_params)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        params = ser.validated_data

        # 2. 데이터 조회
        data = self.get_data(params)

        # 3. format 판별
        fmt = request.query_params.get('export', '')

        if fmt in ('xlsx', 'excel'):
            rows = data if isinstance(data, list) else data.get('daily', [])
            if len(rows) > ASYNC_THRESHOLD:
                rf = ReportFile.objects.create(
                    report_type=self.report_type,
                    params=self._serialize_params(params),
                    created_by=request.user,
                )
                from .tasks import generate_report_excel
                generate_report_excel.delay(rf.id)
                return Response(
                    {'message': '리포트 생성이 요청되었습니다.', 'report_file_id': rf.id},
                    status=status.HTTP_202_ACCEPTED,
                )

            wb = build_workbook(rows, self.excel_columns, self.excel_sheet_title)
            filename = self._build_filename(params)
            return workbook_to_response(wb, filename)

        # 4. JSON
        if isinstance(data, list):
            return Response({'count': len(data), 'results': data})
        return Response(data)

    def _build_filename(self, params):
        parts = [self.excel_filename_prefix]
        if 'date_from' in params:
            parts.append(str(params['date_from']))
            parts.append(str(params['date_to']))
        if 'client_id' in params:
            parts.append(f'client{params["client_id"]}')
        return '_'.join(parts) + '.xlsx'

    @staticmethod
    def _serialize_params(params):
        """date 객체를 문자열로 변환 (JSONField 저장)"""
        out = {}
        for k, v in params.items():
            out[k] = str(v) if hasattr(v, 'isoformat') else v
        return out


# ------------------------------------------------------------------
# 구체 뷰
# ------------------------------------------------------------------

class InventoryLedgerView(BaseReportView):
    """수불부 리포트

    GET /api/v1/reports/inventory-ledger/?client_id=1&date_from=&date_to=
    """
    param_serializer_class = InventoryLedgerParamSerializer
    report_type = 'INVENTORY_LEDGER'
    excel_columns = LEDGER_COLUMNS
    excel_sheet_title = '재고원장'
    excel_filename_prefix = '재고원장'

    def get_data(self, params):
        return services.get_inventory_ledger(
            client_id=params['client_id'],
            date_from=params['date_from'],
            date_to=params['date_to'],
        )


class ShipmentSummaryView(BaseReportView):
    """출고 실적 리포트

    GET /api/v1/reports/shipment-summary/?date_from=&date_to=&client_id=
    """
    param_serializer_class = ShipmentSummaryParamSerializer
    report_type = 'SHIPMENT_SUMMARY'
    excel_columns = SHIPMENT_COLUMNS
    excel_sheet_title = '출고요약'
    excel_filename_prefix = '출고요약'

    def get_data(self, params):
        return services.get_shipment_summary(
            date_from=params['date_from'],
            date_to=params['date_to'],
            client_id=params.get('client_id'),
        )


class WorkerProductivityView(BaseReportView):
    """작업자 생산성 리포트

    GET /api/v1/reports/worker-productivity/?date_from=&date_to=
    """
    param_serializer_class = WorkerProductivityParamSerializer
    report_type = 'WORKER_PRODUCTIVITY'
    excel_columns = WORKER_COLUMNS
    excel_sheet_title = '작업자생산성'
    excel_filename_prefix = '작업자생산성'

    def get_data(self, params):
        return services.get_worker_productivity(
            date_from=params['date_from'],
            date_to=params['date_to'],
        )


class SafetyStockAlertView(BaseReportView):
    """안전재고 미달 리포트

    GET /api/v1/reports/safety-stock-alert/?client_id=
    """
    param_serializer_class = SafetyStockAlertParamSerializer
    report_type = 'SAFETY_STOCK_ALERT'
    excel_columns = SAFETY_COLUMNS
    excel_sheet_title = '안전재고알림'
    excel_filename_prefix = '안전재고알림'

    def get_data(self, params):
        return services.get_safety_stock_alerts(
            client_id=params.get('client_id'),
        )


# ------------------------------------------------------------------
# 비동기 리포트 상태 조회
# ------------------------------------------------------------------

class ReportFileStatusView(APIView):
    """비동기 리포트 상태 조회

    GET /api/v1/reports/files/{id}/
    """
    permission_classes = [IsOfficeStaff]

    def get(self, request, pk):
        try:
            rf = ReportFile.objects.get(pk=pk, created_by=request.user)
        except ReportFile.DoesNotExist:
            return Response(
                {'detail': '리포트를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(ReportFileSerializer(rf).data)
