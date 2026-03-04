"""
웨이브 API URL 설정
"""
from django.urls import path

from . import views

app_name = 'wave-api'

urlpatterns = [
    path('create/', views.WaveCreateView.as_view(), name='wave-create'),
    path('', views.WaveListView.as_view(), name='wave-list'),
    path('<str:wave_id>/', views.WaveDetailView.as_view(), name='wave-detail'),
    path(
        '<str:wave_id>/progress/',
        views.WaveProgressView.as_view(),
        name='wave-progress',
    ),

    # PDA 토탈피킹
    path(
        '<str:wave_id>/picklist/',
        views.PickListView.as_view(),
        name='wave-picklist',
    ),
    path(
        '<str:wave_id>/pick/',
        views.PickScanView.as_view(),
        name='wave-pick',
    ),
]
