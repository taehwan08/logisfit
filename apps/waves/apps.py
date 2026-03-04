from django.apps import AppConfig


class WavesConfig(AppConfig):
    """웨이브 관리 앱 설정"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.waves'
    verbose_name = '웨이브 관리'
