from django.apps import AppConfig


class HistoryConfig(AppConfig):
    """이력 관리 앱 설정"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.history'
    verbose_name = '이력 관리'
