from django.apps import AppConfig


class WebhooksConfig(AppConfig):
    """웹훅 관리 앱 설정"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.webhooks'
    verbose_name = '웹훅 관리'
