"""
반품 관리 URL 설정
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

app_name = 'returns'

router = DefaultRouter()
router.register('orders', views.ReturnOrderViewSet, basename='return-order')

urlpatterns = [
    path('', include(router.urls)),

    # PDA 반품 검수
    path(
        '<str:return_id>/inspect/',
        views.PDAReturnInspectView.as_view(),
        name='pda-return-inspect',
    ),
]
