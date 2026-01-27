"""
Celery 설정 모듈

비동기 작업 처리를 위한 Celery 구성입니다.
청구서 자동 발송 등의 스케줄링 작업에 사용됩니다.
"""
import os
from celery import Celery

# Django 설정 모듈 지정
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

# Celery 앱 생성
app = Celery('logisfit')

# Django 설정에서 Celery 설정 로드
# namespace='CELERY'는 모든 Celery 관련 설정이 CELERY_ 접두사를 가짐을 의미
app.config_from_object('django.conf:settings', namespace='CELERY')

# 등록된 Django 앱에서 태스크 자동 발견
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """디버깅용 태스크"""
    print(f'Request: {self.request!r}')
