"""
입고 관리 URL 설정
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

app_name = 'inbound'

router = DefaultRouter()
router.register('orders', views.InboundOrderViewSet, basename='inbound-order')

urlpatterns = [
    path('', include(router.urls)),
]
