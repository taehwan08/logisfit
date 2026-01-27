# Python 3.11 기반 이미지
FROM python:3.11-slim

# 환경 변수 설정
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV PORT=8000

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 설치 (WeasyPrint 및 PostgreSQL 클라이언트용)
RUN apt-get clean && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# pip 업그레이드
RUN pip install --upgrade pip

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 정적 파일 디렉토리 생성
RUN mkdir -p staticfiles

# 포트 노출
EXPOSE ${PORT}

# 시작 스크립트
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120 --access-logfile - --error-logfile - --capture-output"]
