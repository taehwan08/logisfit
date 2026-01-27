# Celery 앱을 Django와 함께 로드
from .celery import app as celery_app

__all__ = ('celery_app',)
