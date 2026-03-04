"""
재고 외부 제공 API URL 설정
"""
from django.urls import path

from . import api_views

urlpatterns = [
    path('', api_views.InventoryDetailView.as_view(), name='inventory-detail'),
    path('bulk/', api_views.InventoryBulkView.as_view(), name='inventory-bulk'),
]
