"""
WSGI 설정

프로덕션 배포를 위한 WSGI 애플리케이션입니다.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

application = get_wsgi_application()
