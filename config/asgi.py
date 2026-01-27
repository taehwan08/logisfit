"""
ASGI 설정

비동기 웹 서버를 위한 ASGI 애플리케이션입니다.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

application = get_asgi_application()
