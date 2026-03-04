from django.apps import AppConfig


class ReportsConfig(AppConfig):
    """리포트 앱 설정"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.reports'
    verbose_name = '리포트'
