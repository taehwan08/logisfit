"""
외부 연동 어댑터 URL 설정
"""
from django.urls import path

from . import views

app_name = 'adapters'

urlpatterns = [
    path(
        'b2b/upload/',
        views.B2BUploadView.as_view(),
        name='b2b-upload',
    ),
]
