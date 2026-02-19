"""
출고 관리 URL 설정
"""
from django.urls import path
from . import views

app_name = 'fulfillment'

urlpatterns = [
    # 페이지
    path('', views.order_list_page, name='order_list'),

    # 브랜드 API
    path('api/brands/', views.get_brands, name='get_brands'),
    path('api/brands/create/', views.create_brand, name='create_brand'),
    path('api/brands/<int:brand_id>/update/', views.update_brand, name='update_brand'),
    path('api/brands/<int:brand_id>/delete/', views.delete_brand, name='delete_brand'),

    # 주문 API
    path('api/orders/', views.get_orders, name='get_orders'),
    path('api/orders/create/', views.create_order, name='create_order'),
    path('api/orders/bulk-paste/', views.bulk_paste_orders, name='bulk_paste_orders'),
    path('api/orders/<int:order_id>/update/', views.update_order, name='update_order'),
    path('api/orders/<int:order_id>/delete/', views.delete_order, name='delete_order'),
    path('api/orders/<int:order_id>/status/', views.update_status, name='update_status'),
    path('api/orders/export/', views.export_excel, name='export_excel'),

    # 댓글 API
    path('api/orders/<int:order_id>/comments/', views.get_comments, name='get_comments'),
    path('api/orders/<int:order_id>/comments/add/', views.add_comment, name='add_comment'),
    path('api/orders/<int:order_id>/comments/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),
]
