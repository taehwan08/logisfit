from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """계정 앱 설정"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    verbose_name = '사용자 관리'
