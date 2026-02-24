"""
세션 관리 미들웨어

동시 로그인 방지를 위한 미들웨어입니다.
다른 브라우저/기기에서 로그인하면 이전 세션이 무효화됩니다.
"""
import logging

from django.contrib.auth import logout
from django.contrib import messages

logger = logging.getLogger(__name__)


class SingleSessionMiddleware:
    """
    단일 세션 미들웨어

    사용자가 다른 곳에서 로그인하여 현재 세션이 무효화된 경우,
    자동으로 로그아웃 처리합니다.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            current_session_key = request.session.session_key
            stored_session_key = request.user.session_key

            if stored_session_key and current_session_key != stored_session_key:
                logger.info(
                    '세션 무효화: 사용자 %s의 세션이 다른 곳에서의 로그인으로 인해 종료됩니다.',
                    request.user.email,
                )
                logout(request)
                messages.warning(
                    request,
                    '다른 기기에서 로그인이 감지되어 자동으로 로그아웃되었습니다.',
                )

        response = self.get_response(request)
        return response
