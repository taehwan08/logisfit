"""
리포트 페이지 URL 설정

API URL(apps/reports/urls.py)과 분리된 페이지 전용 URL.
config/urls.py에서 path('reports/', include('apps.reports.page_urls'))로 등록.
"""
from django.urls import path

from .page_views import DailyParcelReportView

app_name = 'reports_page'

urlpatterns = [
    path('daily-parcel/', DailyParcelReportView.as_view(), name='daily_parcel'),
]
