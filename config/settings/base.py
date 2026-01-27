"""
Django 기본 설정

모든 환경에서 공통으로 사용되는 설정입니다.
환경별 설정은 local.py, production.py에서 오버라이드합니다.
"""
import os
from pathlib import Path
import environ

# 환경 변수 로드
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ['localhost', '127.0.0.1']),
)

# 프로젝트 루트 디렉토리
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# .env 파일 로드 (파일이 있을 경우만)
env_file = os.path.join(BASE_DIR, '.env')
if os.path.exists(env_file):
    environ.Env.read_env(env_file)

# 보안 키 (Railway에서는 환경변수로 설정 필요)
SECRET_KEY = env('SECRET_KEY', default='django-insecure-change-this-in-production')

# 디버그 모드
DEBUG = env('DEBUG')

# 허용된 호스트
ALLOWED_HOSTS = env('ALLOWED_HOSTS')


# ============================================================================
# 애플리케이션 정의
# ============================================================================

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',  # 숫자 포맷팅 등
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'corsheaders',
    'widget_tweaks',
]

LOCAL_APPS = [
    'apps.accounts',
    # Phase 2 이후 추가될 앱들
    # 'apps.clients',
    # 'apps.works',
    # 'apps.storage',
    # 'apps.invoices',
    # 'apps.contracts',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# ============================================================================
# 미들웨어
# ============================================================================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# ============================================================================
# URL 설정
# ============================================================================

ROOT_URLCONF = 'config.urls'


# ============================================================================
# 템플릿 설정
# ============================================================================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


# ============================================================================
# WSGI/ASGI
# ============================================================================

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'


# ============================================================================
# 데이터베이스
# ============================================================================

DATABASES = {
    'default': env.db('DATABASE_URL', default='sqlite:///db.sqlite3'),
}


# ============================================================================
# 비밀번호 유효성 검사
# ============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        },
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# ============================================================================
# 사용자 모델
# ============================================================================

AUTH_USER_MODEL = 'accounts.User'


# ============================================================================
# 국제화
# ============================================================================

LANGUAGE_CODE = 'ko-kr'

TIME_ZONE = env('TIME_ZONE', default='Asia/Seoul')

USE_I18N = True

USE_TZ = True


# ============================================================================
# 정적 파일 (CSS, JavaScript, Images)
# ============================================================================

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'


# ============================================================================
# 미디어 파일 (업로드)
# ============================================================================

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ============================================================================
# 기본 기본키 필드 타입
# ============================================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ============================================================================
# 인증 설정
# ============================================================================

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'accounts:login'


# ============================================================================
# Django REST Framework
# ============================================================================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}


# ============================================================================
# Celery 설정
# ============================================================================

CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30분


# ============================================================================
# 이메일 설정
# ============================================================================

EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@logisfit.com')


# ============================================================================
# CORS 설정
# ============================================================================

CORS_ALLOW_ALL_ORIGINS = DEBUG  # 개발 환경에서만 모든 출처 허용
