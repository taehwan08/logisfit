"""
API URL 설정

DRF 라우터를 사용한 API URL 패턴을 정의합니다.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api_views import UserViewSet
from .dashboard_views import (
    ClientDashboardView,
    FieldDashboardView,
    OfficeDashboardView,
)

# DRF 라우터 설정
router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/office/', OfficeDashboardView.as_view(), name='dashboard-office'),
    path('dashboard/field/', FieldDashboardView.as_view(), name='dashboard-field'),
    path('dashboard/client/', ClientDashboardView.as_view(), name='dashboard-client'),
]
