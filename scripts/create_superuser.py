#!/usr/bin/env python
"""
환경변수 기반 superuser 자동 생성 스크립트
"""
import os
import sys
import django

# Django 설정 로드
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
name = os.environ.get('DJANGO_SUPERUSER_NAME', 'Admin')

if not email or not password:
    print('DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD must be set')
    sys.exit(0)

if User.objects.filter(email=email).exists():
    print(f'Superuser {email} already exists')
else:
    User.objects.create_superuser(email=email, password=password, name=name)
    print(f'Superuser {email} created successfully')
