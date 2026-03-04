"""
출력 관리 URL 설정
"""
from django.urls import path

from . import views

app_name = 'printing'

urlpatterns = [
    path(
        'pending/',
        views.PendingPrintJobsView.as_view(),
        name='pending-jobs',
    ),
    path(
        'reprint/<int:print_job_id>/',
        views.ReprintView.as_view(),
        name='reprint',
    ),
]
