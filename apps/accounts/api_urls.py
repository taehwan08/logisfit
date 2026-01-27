"""
API URL 설정

DRF 라우터를 사용한 API URL 패턴을 정의합니다.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api_views import UserViewSet

# DRF 라우터 설정
router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    path('', include(router.urls)),
]
