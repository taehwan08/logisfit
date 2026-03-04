"""
이력 관리 URL 설정
"""
from django.urls import path

from . import views

app_name = 'history'

urlpatterns = [
    path(
        'transactions/',
        views.InventoryTransactionListView.as_view(),
        name='transaction-list',
    ),
]
