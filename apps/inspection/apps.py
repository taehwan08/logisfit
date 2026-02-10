"""
inspection 앱 설정
"""
from django.apps import AppConfig


class InspectionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inspection'
    verbose_name = '바코드 검수'
