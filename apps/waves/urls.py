"""
웨이브 관리 URL 설정
"""
from django.urls import path

from . import views

app_name = 'waves'

urlpatterns = [
    # 주문 수신
    path('', views.OrderReceiveView.as_view(), name='order-receive'),
    # 주문 취소
    path(
        '<str:wms_order_id>/cancel/',
        views.OrderCancelView.as_view(),
        name='order-cancel',
    ),
]
