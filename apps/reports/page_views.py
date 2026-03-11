"""
리포트 페이지 뷰 (독립 모듈)

기존 API 뷰(views.py)와 분리하여 import 의존성을 최소화한다.
"""
import os

from django.http import HttpResponse
from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from .daily_parcel import process_daily_parcel_report


class ReportAdminMixin(LoginRequiredMixin, UserPassesTestMixin):
    """리포트용 관리자 권한 믹스인"""

    def test_func(self):
        return self.request.user.is_admin or self.request.user.is_superuser

    def handle_no_permission(self):
        from django.shortcuts import redirect
        from django.contrib import messages
        messages.error(self.request, '관리자 권한이 필요합니다.')
        return redirect('dashboard')


class DailyParcelReportView(ReportAdminMixin, View):
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
