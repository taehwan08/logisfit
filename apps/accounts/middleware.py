"""
세션 관리 미들웨어

비밀번호 변경 시 다른 모든 세션을 무효화하기 위한 미들웨어입니다.
User.password_changed_at 값이 세션에 저장된 시점보다 새로우면 자동 로그아웃합니다.
"""
import logging

from django.contrib.auth import logout
from django.contrib import messages

logger = logging.getLogger(__name__)

# 세션에 저장할 키 이름
SESSION_PASSWORD_TIMESTAMP_KEY = '_pw_changed_at'


class PasswordChangeLogoutMiddleware:
    """
    비밀번호 변경 감지 미들웨어

    비밀번호가 변경되면 현재 세션을 제외한 다른 모든 세션이 로그아웃됩니다.
    동작 원리:
    1. 로그인 시 세션에 password_changed_at 타임스탬프 저장
    2. 매 요청마다 세션의 타임스탬프 vs DB의 타임스탬프 비교
    3. DB가 더 최신이면 → 다른 기기에서 비밀번호가 변경된 것 → 로그아웃
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # DB의 비밀번호 변경 시점
            db_timestamp = request.user.password_changed_at
            if db_timestamp:
                # 세션에 저장된 비밀번호 변경 시점
                session_timestamp = request.session.get(SESSION_PASSWORD_TIMESTAMP_KEY)

                if session_timestamp is None:
                    # 최초 접속 또는 기존 세션 — 현재 시점 기록
                    request.session[SESSION_PASSWORD_TIMESTAMP_KEY] = db_timestamp.isoformat()
                elif session_timestamp < db_timestamp.isoformat():
                    # 비밀번호가 변경된 후의 세션 → 로그아웃
                    logger.info(
                        '비밀번호 변경 감지: 사용자 %s의 세션이 종료됩니다.',
                        request.user.email,
                    )
                    logout(request)
                    messages.warning(
                        request,
                        '비밀번호가 변경되어 자동으로 로그아웃되었습니다. 새 비밀번호로 다시 로그인해주세요.',
                    )

        response = self.get_response(request)
        return response
