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

    # PDA 전용 API
    path(
        '<str:inbound_id>/inspect/',
        views.PDAInspectView.as_view(),
        name='pda-inspect',
    ),
    path(
        '<str:inbound_id>/putaway/',
        views.PDAPutawayView.as_view(),
        name='pda-putaway',
    ),
    path(
        'suggest-location/',
        views.SuggestLocationView.as_view(),
        name='suggest-location',
    ),
]
