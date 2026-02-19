"""
출고 관리 URL 설정
"""
from django.urls import path
from . import views

app_name = 'fulfillment'

urlpatterns = [
    # 페이지
    path('', views.order_list_page, name='order_list'),

    # API
    path('api/orders/', views.get_orders, name='get_orders'),
    path('api/orders/create/', views.create_order, name='create_order'),
    path('api/orders/<int:order_id>/update/', views.update_order, name='update_order'),
    path('api/orders/<int:order_id>/delete/', views.delete_order, name='delete_order'),
    path('api/orders/<int:order_id>/status/', views.update_status, name='update_status'),
    path('api/orders/export/', views.export_excel, name='export_excel'),
    path('api/orders/template/', views.download_template, name='download_template'),
    path('api/orders/upload/', views.upload_orders_excel, name='upload_orders_excel'),

    # 댓글 API
    path('api/orders/<int:order_id>/comments/', views.get_comments, name='get_comments'),
    path('api/orders/<int:order_id>/comments/add/', views.add_comment, name='add_comment'),
    path('api/orders/<int:order_id>/comments/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),
]
