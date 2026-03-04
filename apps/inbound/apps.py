from django.apps import AppConfig


class InboundConfig(AppConfig):
    """입고 관리 앱 설정"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inbound'
    verbose_name = '입고 관리'
