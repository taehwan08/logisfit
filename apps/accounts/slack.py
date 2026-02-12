"""
Slack 연동 모듈

회원가입 알림 전송 및 슬랙 버튼을 통한 승인/거절 처리를 담당합니다.
"""
import hashlib
import hmac
import json
import logging
import time

import requests
from django.conf import settings
from django.utils import timezone

from .models import User

logger = logging.getLogger(__name__)

ROLE_LABELS = dict(User.Role.choices)


def send_signup_notification(user):
    """회원가입 시 슬랙 채널에 알림 메시지를 전송한다.

    Block Kit 형식으로 사용자 정보와 승인/거절 버튼을 포함한다.
    SLACK_WEBHOOK_URL이 설정되지 않으면 아무 동작도 하지 않는다.
    """
    webhook_url = getattr(settings, 'SLACK_WEBHOOK_URL', '')
    if not webhook_url:
        logger.debug('SLACK_WEBHOOK_URL이 설정되지 않아 알림을 건너뜁니다.')
        return

    site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
    role_label = ROLE_LABELS.get(user.role, user.role)
    created_at = timezone.localtime(user.created_at).strftime('%Y-%m-%d %H:%M')
    approval_url = f'{site_url}/accounts/users/{user.pk}/approve/'

    blocks = [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': '새로운 가입 요청',
                'emoji': True,
            },
        },
        {
            'type': 'section',
            'fields': [
                {'type': 'mrkdwn', 'text': f'*이름:*\n{user.name}'},
                {'type': 'mrkdwn', 'text': f'*이메일:*\n{user.email}'},
                {'type': 'mrkdwn', 'text': f'*역할:*\n{role_label}'},
                {'type': 'mrkdwn', 'text': f'*연락처:*\n{user.phone or "-"}'},
            ],
        },
        {
            'type': 'context',
            'elements': [
                {'type': 'mrkdwn', 'text': f'가입일시: {created_at}'},
            ],
        },
        {'type': 'divider'},
        {
            'type': 'actions',
            'elements': [
                {
                    'type': 'button',
                    'text': {'type': 'plain_text', 'text': '승인', 'emoji': True},
                    'style': 'primary',
                    'action_id': 'approve_user',
                    'value': json.dumps({
                        'user_id': user.pk,
                        'action': 'approve',
                    }),
                },
                {
                    'type': 'button',
                    'text': {'type': 'plain_text', 'text': '거절', 'emoji': True},
                    'style': 'danger',
                    'action_id': 'reject_user',
                    'value': json.dumps({
                        'user_id': user.pk,
                        'action': 'reject',
                    }),
                },
                {
                    'type': 'button',
                    'text': {'type': 'plain_text', 'text': '관리 페이지', 'emoji': True},
                    'url': approval_url,
                    'action_id': 'open_approval_page',
                },
            ],
        },
    ]

    payload = {
        'text': f'새로운 가입 요청: {user.name} ({user.email})',
        'blocks': blocks,
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.warning(
                'Slack 알림 전송 실패: status=%s body=%s',
                resp.status_code,
                resp.text[:200],
            )
    except requests.RequestException as e:
        logger.warning('Slack 알림 전송 중 네트워크 오류: %s', e)


def verify_slack_signature(request):
    """Slack 요청의 서명을 검증한다.

    Returns:
        bool: 서명이 유효하면 True
    """
    signing_secret = getattr(settings, 'SLACK_SIGNING_SECRET', '')
    if not signing_secret:
        # Signing Secret이 설정되지 않으면 검증 건너뜀 (개발 편의)
        logger.warning('SLACK_SIGNING_SECRET이 설정되지 않아 서명 검증을 건너뜁니다.')
        return True

    timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
    signature = request.headers.get('X-Slack-Signature', '')

    if not timestamp or not signature:
        return False

    # 5분 이상 된 요청은 거부 (리플레이 공격 방지)
    try:
        if abs(time.time() - int(timestamp)) > 60 * 5:
            return False
    except (ValueError, TypeError):
        return False

    sig_basestring = f'v0:{timestamp}:{request.body.decode("utf-8")}'
    computed = 'v0=' + hmac.new(
        signing_secret.encode('utf-8'),
        sig_basestring.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, signature)


def process_slack_action(payload):
    """슬랙 interactive 버튼 클릭을 처리한다.

    Args:
        payload: 슬랙에서 전달한 interaction payload (dict)

    Returns:
        dict: 슬랙에 응답할 메시지 (replace_original)
    """
    actions = payload.get('actions', [])
    if not actions:
        return {'text': '처리할 액션이 없습니다.'}

    action = actions[0]
    action_id = action.get('action_id', '')

    # 관리 페이지 링크 버튼은 별도 처리 불필요
    if action_id == 'open_approval_page':
        return None

    try:
        value = json.loads(action.get('value', '{}'))
    except (json.JSONDecodeError, TypeError):
        return _error_response('잘못된 요청입니다.')

    user_id = value.get('user_id')
    action_type = value.get('action')

    if not user_id or action_type not in ('approve', 'reject'):
        return _error_response('잘못된 요청입니다.')

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return _error_response('해당 사용자를 찾을 수 없습니다.')

    # 이미 처리된 사용자인지 확인
    if user.is_approved:
        return _already_processed_response(user, '이미 승인된 사용자입니다.')

    if not user.is_active:
        return _already_processed_response(user, '이미 거절(비활성화)된 사용자입니다.')

    # 슬랙에서 누른 사람 정보
    slack_user = payload.get('user', {})
    slack_username = slack_user.get('name', '알 수 없음')

    now = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M')

    if action_type == 'approve':
        user.is_approved = True
        user.save(update_fields=['is_approved'])
        return _result_response(user, slack_username, now, approved=True)
    else:
        user.is_active = False
        user.save(update_fields=['is_active'])
        return _result_response(user, slack_username, now, approved=False)


def _result_response(user, slack_username, timestamp, approved):
    """승인/거절 완료 후 슬랙 메시지를 업데이트한다."""
    role_label = ROLE_LABELS.get(user.role, user.role)

    if approved:
        emoji = ':white_check_mark:'
        status_text = '승인 완료'
        color = '#28a745'
    else:
        emoji = ':x:'
        status_text = '거절'
        color = '#dc3545'

    blocks = [
        {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': (
                    f'{emoji} *{user.name}* ({user.email}) - *{status_text}*\n'
                    f'역할: {role_label} | 연락처: {user.phone or "-"}'
                ),
            },
        },
        {
            'type': 'context',
            'elements': [
                {
                    'type': 'mrkdwn',
                    'text': f'처리자: @{slack_username} | {timestamp}',
                },
            ],
        },
    ]

    return {
        'replace_original': True,
        'blocks': blocks,
    }


def _error_response(message):
    """오류 응답 메시지를 생성한다."""
    return {
        'replace_original': False,
        'response_type': 'ephemeral',
        'text': f':warning: {message}',
    }


def _already_processed_response(user, message):
    """이미 처리된 사용자에 대한 응답 메시지를 생성한다."""
    return {
        'replace_original': False,
        'response_type': 'ephemeral',
        'text': f':information_source: {message} ({user.name} / {user.email})',
    }
