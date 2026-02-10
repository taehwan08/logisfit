"""
검수 시스템 URL 설정
"""
from django.urls import path
from . import views

app_name = 'inspection'

urlpatterns = [
    # 오피스팀용 페이지
    path('office/', views.office_page, name='office_page'),

    # 필드팀용 페이지
    path('field/', views.field_page, name='field_page'),

    # API
    path('upload/', views.upload_excel, name='upload_excel'),
    path('api/orders/<str:tracking_number>/', views.get_order, name='get_order'),
    path('api/orders/', views.get_orders_status, name='get_orders_status'),
    path('api/scan/product/', views.scan_product, name='scan_product'),
    path('api/scan/complete/', views.complete_inspection, name='complete_inspection'),
    path('api/logs/', views.get_logs, name='get_logs'),
]
