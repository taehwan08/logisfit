from django.apps import AppConfig


class AdaptersConfig(AppConfig):
    """외부 연동 어댑터 앱 설정"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.adapters'
    verbose_name = '외부 연동'
