from django.apps import AppConfig


class ReturnsConfig(AppConfig):
    """반품 관리 앱 설정"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.returns'
    verbose_name = '반품 관리'
