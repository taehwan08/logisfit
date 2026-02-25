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
    path('products/', views.products_page, name='products_page'),

    # API: 상품 마스터
    path('api/products/', views.get_products, name='get_products'),
    path('api/products/create/', views.create_product, name='create_product'),
    path('api/products/<int:product_id>/update/', views.update_product, name='update_product'),
    path('api/products/<int:product_id>/delete/', views.delete_product, name='delete_product'),
    path('api/products/upload/', views.upload_products_excel, name='upload_products_excel'),
    path('api/products/lookup/', views.lookup_product, name='lookup_product'),

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
    path('api/records/export/', views.export_records_excel, name='export_records_excel'),

    # 입고 관리
    path('inbound/', views.inbound_page, name='inbound_page'),
    path('api/inbound/', views.get_inbound_records, name='get_inbound_records'),
    path('api/inbound/create/', views.create_inbound, name='create_inbound'),
    path('api/inbound/<int:record_id>/complete/', views.complete_inbound, name='complete_inbound'),
]
