"""
리포트 페이지 URL 설정

API URL(apps/reports/urls.py)과 분리된 페이지 전용 URL.
config/urls.py에서 path('reports/', include('apps.reports.page_urls'))로 등록.
"""
from django.urls import path

from .page_views import (
    DailyParcelUploadView,
    DailyParcelReportView,
    DailyParcelExcelView,
)

app_name = 'reports_page'

urlpatterns = [
    path('daily-parcel/', DailyParcelUploadView.as_view(), name='daily_parcel'),
    path('daily-parcel/<str:date>/', DailyParcelReportView.as_view(), name='daily_parcel_report'),
    path('daily-parcel/<str:date>/excel/', DailyParcelExcelView.as_view(), name='daily_parcel_excel'),
]
