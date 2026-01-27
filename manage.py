#!/usr/bin/env python
"""Django 관리 명령어 유틸리티."""
import os
import sys


def main():
    """관리 작업을 실행합니다."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django를 가져올 수 없습니다. 가상 환경이 활성화되어 있고 "
            "Django가 설치되어 있는지 확인하세요. "
            "또한 PYTHONPATH 환경 변수를 확인하세요."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
