"""
리포트 페이지 뷰 (독립 모듈)

기존 API 뷰(views.py)와 분리하여 import 의존성을 최소화한다.
"""
import os
from datetime import date, timedelta

from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction

from .models import DailyParcelReport, DailyParcelBrand
from .daily_parcel import parse_parcel_excel, generate_report_excel


class ReportAdminMixin(LoginRequiredMixin, UserPassesTestMixin):
    """리포트용 관리자 권한 믹스인"""

    def test_func(self):
        return self.request.user.is_admin or self.request.user.is_superuser

    def handle_no_permission(self):
        messages.error(self.request, '관리자 권한이 필요합니다.')
        return redirect('dashboard')


class DailyParcelUploadView(ReportAdminMixin, View):
    """일일택배사업부 — 업로드 페이지

    GET: 업로드 폼 + 최근 리포트 목록
    POST: 엑셀 파싱 → DB 저장 → 리포트 페이지로 리다이렉트
    """
    template_name = 'reports/daily_parcel_upload.html'

    def get(self, request):
        recent_reports = DailyParcelReport.objects.select_related('uploaded_by')[:20]
        return render(request, self.template_name, {
            'recent_reports': recent_reports,
        })

    def post(self, request):
        uploaded_file = request.FILES.get('excel_file')
        report_date_str = request.POST.get('report_date', '')

        if not uploaded_file:
            messages.error(request, '파일을 선택해주세요.')
            return redirect('reports_page:daily_parcel')

        # 확장자 검증
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in ('.xls', '.xlsx'):
            messages.error(request, '엑셀 파일(.xls 또는 .xlsx)만 업로드 가능합니다.')
            return redirect('reports_page:daily_parcel')

        # 날짜 검증
        try:
            report_date = date.fromisoformat(report_date_str)
        except (ValueError, TypeError):
            messages.error(request, '리포트 날짜를 선택해주세요.')
            return redirect('reports_page:daily_parcel')

        # 엑셀 파싱
        try:
            result = parse_parcel_excel(uploaded_file)
        except Exception as e:
            messages.error(request, f'파일 처리 오류: {str(e)}')
            return redirect('reports_page:daily_parcel')

        # DB 저장 (같은 날짜면 덮어쓰기)
        with transaction.atomic():
            report, created = DailyParcelReport.objects.update_or_create(
                report_date=report_date,
                defaults={
                    'file_name': uploaded_file.name,
                    'total_orders': result['total_orders'],
                    'single_count': result['total_single'],
                    'combo_count': result['total_combo'],
                    'uploaded_by': request.user,
                },
            )
            # 기존 브랜드 데이터 삭제 후 재생성
            report.brands.all().delete()
            brand_objects = []
            for brand_name, counts in result['brands'].items():
                brand_objects.append(DailyParcelBrand(
                    report=report,
                    brand_name=brand_name,
                    single_count=counts['single'],
                    combo_count=counts['combo'],
                    total_count=counts['single'] + counts['combo'],
                ))
            DailyParcelBrand.objects.bulk_create(brand_objects)

        action = '업데이트' if not created else '등록'
        messages.success(request, f'{report_date} 리포트가 {action}되었습니다. (총 {result["total_orders"]}건)')
        return redirect('reports_page:daily_parcel_report', date=str(report_date))


class DailyParcelReportView(ReportAdminMixin, View):
    """일일택배사업부 — 리포트 조회 페이지

    날짜별 출고 분석 결과를 요약카드 + 테이블 + 차트로 표시
    """
    template_name = 'reports/daily_parcel_report.html'

    def get(self, request, date):
        report = get_object_or_404(
            DailyParcelReport.objects.prefetch_related('brands'),
            report_date=date,
        )
        brand_list = report.brands.all().order_by('-total_count')

        # 이전/다음 리포트 날짜
        prev_report = (
            DailyParcelReport.objects
            .filter(report_date__lt=report.report_date)
            .order_by('-report_date')
            .values_list('report_date', flat=True)
            .first()
        )
        next_report = (
            DailyParcelReport.objects
            .filter(report_date__gt=report.report_date)
            .order_by('report_date')
            .values_list('report_date', flat=True)
            .first()
        )

        return render(request, self.template_name, {
            'report': report,
            'brand_list': brand_list,
            'prev_date': prev_report,
            'next_date': next_report,
        })


class DailyParcelExcelView(ReportAdminMixin, View):
    """일일택배사업부 — 엑셀 다운로드"""

    def get(self, request, date):
        report = get_object_or_404(
            DailyParcelReport.objects.prefetch_related('brands'),
            report_date=date,
        )
        output = generate_report_excel(report)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        filename = f'일일택배사업부_{report.report_date}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
