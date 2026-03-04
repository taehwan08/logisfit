"""
웹훅 서비스

이벤트 발행 및 배달 로직을 담당합니다.
"""
import hashlib
import hmac
import json
import logging

import requests
from django.utils import timezone

from .models import WebhookSubscriber, WebhookLog

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
DELIVERY_TIMEOUT = 10  # 초


def publish_event(event_type, payload):
    """이벤트 발행

    해당 event_type을 구독하는 활성 구독자를 조회하고
    각 구독자에 대해 비동기 배달 태스크를 발행합니다.

    Args:
        event_type: WebhookEvents 상수
        payload: 이벤트 페이로드 (dict, JSON 직렬화 가능)
    """
    all_active = WebhookSubscriber.objects.filter(is_active=True)
    subscribers = [s for s in all_active if event_type in (s.events or [])]

    if not subscribers:
        return

    from .tasks import deliver_webhook
    for subscriber in subscribers:
        deliver_webhook.delay(subscriber.id, event_type, payload)

    logger.info(
        'Webhook published: event=%s subscribers=%d',
        event_type, len(subscribers),
    )


def deliver(subscriber_id, event_type, payload):
    """웹훅 배달 실행

    1. subscriber URL로 POST 요청
    2. secret_key가 있으면 HMAC-SHA256 서명 추가
    3. 성공 → WebhookLog(success=True)
    4. 실패 → WebhookLog(success=False)

    Returns:
        WebhookLog: 생성된 로그 레코드
    """
    try:
        subscriber = WebhookSubscriber.objects.get(pk=subscriber_id)
    except WebhookSubscriber.DoesNotExist:
        logger.error('WebhookSubscriber %s not found', subscriber_id)
        return None

    body = json.dumps(payload, ensure_ascii=False, default=str)

    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Event': event_type,
    }

    # HMAC-SHA256 서명
    if subscriber.secret_key:
        signature = hmac.new(
            subscriber.secret_key.encode('utf-8'),
            body.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        headers['X-Webhook-Signature'] = signature

    log = WebhookLog.objects.create(
        subscriber=subscriber,
        event=event_type,
        payload=payload,
    )

    try:
        resp = requests.post(
            subscriber.url,
            data=body,
            headers=headers,
            timeout=DELIVERY_TIMEOUT,
        )
        log.status_code = resp.status_code
        log.attempts += 1

        if 200 <= resp.status_code < 300:
            log.success = True
        else:
            log.error_message = f'HTTP {resp.status_code}'

    except requests.RequestException as e:
        log.attempts += 1
        log.error_message = str(e)

    log.save(update_fields=[
        'status_code', 'attempts', 'success', 'error_message',
    ])

    if log.success:
        logger.info(
            'Webhook delivered: subscriber=%s event=%s',
            subscriber.name, event_type,
        )
    else:
        logger.warning(
            'Webhook failed: subscriber=%s event=%s error=%s',
            subscriber.name, event_type, log.error_message,
        )

    return log
