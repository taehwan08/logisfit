"""
웹훅 관리 URL 설정
"""
from django.urls import path

from . import views

app_name = 'webhooks'

urlpatterns = [
    path(
        'subscribers/',
        views.WebhookSubscriberListView.as_view(),
        name='subscriber-list',
    ),
    path(
        'subscribers/<int:pk>/',
        views.WebhookSubscriberDetailView.as_view(),
        name='subscriber-detail',
    ),
    path(
        'logs/',
        views.WebhookLogListView.as_view(),
        name='log-list',
    ),
]
