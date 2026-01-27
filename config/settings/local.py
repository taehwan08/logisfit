"""
Django 로컬 개발 환경 설정

개발 시 사용되는 설정입니다.
DEBUG 모드 활성화, 상세한 에러 메시지 등을 포함합니다.
"""
from .base import *

# 디버그 모드 강제 활성화
DEBUG = True

# 로컬 개발용 호스트
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

# 디버그 툴바 (선택적)
if DEBUG:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
    INTERNAL_IPS = ['127.0.0.1', 'localhost']

    # Docker에서 실행 시 Internal IPs 설정
    import socket
    hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS += [".".join(ip.split(".")[:-1] + ["1"]) for ip in ips]

# 개발용 이메일 설정 (콘솔 출력)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# 로깅 설정
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}
