"""
리포트 URL 설정
"""
from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path(
        'inventory-ledger/',
        views.InventoryLedgerView.as_view(),
        name='inventory-ledger',
    ),
    path(
        'shipment-summary/',
        views.ShipmentSummaryView.as_view(),
        name='shipment-summary',
    ),
    path(
        'worker-productivity/',
        views.WorkerProductivityView.as_view(),
        name='worker-productivity',
    ),
    path(
        'safety-stock-alert/',
        views.SafetyStockAlertView.as_view(),
        name='safety-stock-alert',
    ),
    path(
        'files/<int:pk>/',
        views.ReportFileStatusView.as_view(),
        name='report-file-status',
    ),
]
