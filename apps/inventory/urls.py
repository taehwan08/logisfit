"""
재고 관리 URL 설정
"""
from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # 페이지
    path('', views.session_page, name='session_page'),
    path('scan/', views.scan_page, name='scan_page'),
    path('status/', views.status_page, name='status_page'),

    # API: 세션
    path('api/sessions/', views.get_sessions, name='get_sessions'),
    path('api/sessions/create/', views.create_session, name='create_session'),
    path('api/sessions/<int:session_id>/end/', views.end_session, name='end_session'),

    # API: 스캔
    path('api/scan/location/', views.scan_location, name='scan_location'),
    path('api/scan/product/', views.scan_product, name='scan_product'),

    # API: 기록
    path('api/records/', views.get_records, name='get_records'),
    path('api/records/location/', views.get_location_records, name='get_location_records'),
    path('api/records/<int:record_id>/delete/', views.delete_record, name='delete_record'),
]
