"""
출고 관리 앱 설정
"""
from django.apps import AppConfig


class FulfillmentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.fulfillment'
    verbose_name = '출고 관리'
