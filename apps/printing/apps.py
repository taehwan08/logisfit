from django.apps import AppConfig


class PrintingConfig(AppConfig):
    """출력 관리 앱 설정"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.printing'
    verbose_name = '출력 관리'
